"""TTS client tests: caching, WAV framing, rate limiting and 429 retry.

The network call is stubbed at the SDK boundary, so the real caching, throttling
and retry logic in app/tts.py is exercised.
"""
from __future__ import annotations

import struct
import wave

import pytest

import app.llm as llm_mod
import app.tts as tts


PCM = b"".join(struct.pack("<h", (i % 300) * 50 - 6000) for i in range(24_000))


class _FakeResponse:
    def __init__(self, pcm: bytes = PCM):
        part = type("Part", (), {"inline_data": type("D", (), {"data": pcm})()})()
        content = type("Content", (), {"parts": [part]})()
        self.candidates = [type("Cand", (), {"content": content})()]


class _RateLimited(Exception):
    """Mimics the SDK's 429 surface."""
    def __str__(self) -> str:
        return "429 RESOURCE_EXHAUSTED: quota exceeded"


class FakeModels:
    def __init__(self, fail_times: int = 0):
        self.calls: list[dict] = []
        self.fail_times = fail_times

    def generate_content(self, **kw):
        self.calls.append(kw)
        if len(self.calls) <= self.fail_times:
            raise _RateLimited()
        return _FakeResponse()


@pytest.fixture
def fake_api(monkeypatch):
    """Stub the SDK client and disable throttling sleeps by default."""
    models = FakeModels()
    monkeypatch.setattr(llm_mod, "_client", type("C", (), {"models": models})())
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(tts.config, "GEMINI_API_KEYS", [tts.config.GEMINI_API_KEY])
    monkeypatch.setattr(tts, "_last_call_at", 0.0)
    yield models
    llm_mod._client = None


# --------------------------------------------------------------------------- #
# rendering + WAV framing
# --------------------------------------------------------------------------- #
def test_render_line_writes_a_valid_wav(fake_api, tmp_path):
    out = tts.render_line("Hello there.", "Kore", tmp_path / "a.wav")
    assert out.exists()
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == tts.config.TTS_CHANNELS
        assert wf.getsampwidth() == tts.config.TTS_SAMPLE_WIDTH
        assert wf.getframerate() == tts.config.TTS_SAMPLE_RATE
        assert wf.getnframes() == len(PCM) // 2


def test_render_line_creates_missing_parent_dirs(fake_api, tmp_path):
    out = tts.render_line("Hi.", "Kore", tmp_path / "deep" / "nest" / "a.wav")
    assert out.exists()


def test_render_line_passes_the_requested_voice(fake_api, tmp_path):
    tts.render_line("Hi.", "Algenib", tmp_path / "a.wav")
    cfg = fake_api.calls[0]["config"]
    voice = cfg.speech_config.voice_config.prebuilt_voice_config.voice_name
    assert voice == "Algenib"
    assert cfg.response_modalities == ["AUDIO"]
    assert fake_api.calls[0]["model"] == tts.config.TTS_MODEL


# --------------------------------------------------------------------------- #
# caching
# --------------------------------------------------------------------------- #
def test_identical_line_is_synthesised_once(fake_api, tmp_path):
    cache = tmp_path / "cache"
    tts.render_line("Same line.", "Kore", tmp_path / "1.wav", cache_dir=cache)
    tts.render_line("Same line.", "Kore", tmp_path / "2.wav", cache_dir=cache)

    assert len(fake_api.calls) == 1, "cache miss on an identical line"
    assert (tmp_path / "1.wav").read_bytes() == (tmp_path / "2.wav").read_bytes()


def test_cache_is_keyed_on_text_and_voice(fake_api, tmp_path):
    cache = tmp_path / "cache"
    tts.render_line("Line A.", "Kore", tmp_path / "1.wav", cache_dir=cache)
    tts.render_line("Line B.", "Kore", tmp_path / "2.wav", cache_dir=cache)   # new text
    tts.render_line("Line A.", "Leda", tmp_path / "3.wav", cache_dir=cache)   # new voice
    assert len(fake_api.calls) == 3


def test_no_cache_dir_means_no_caching(fake_api, tmp_path):
    tts.render_line("Same.", "Kore", tmp_path / "1.wav")
    tts.render_line("Same.", "Kore", tmp_path / "2.wav")
    assert len(fake_api.calls) == 2


def test_cache_key_is_stable_and_model_scoped():
    a = tts._cache_key("hello", "Kore")
    assert a == tts._cache_key("hello", "Kore")
    assert a != tts._cache_key("hello", "Leda")
    assert a != tts._cache_key("hello!", "Kore")


# --------------------------------------------------------------------------- #
# rate limiting + retry (the free-tier ~3 req/min guardrail)
# --------------------------------------------------------------------------- #
def test_calls_are_spaced_by_the_configured_interval(fake_api, tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(tts.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 21.0)
    monkeypatch.setattr(tts, "_last_call_at", tts.time.monotonic())

    tts.render_line("One.", "Kore", tmp_path / "1.wav")
    assert slept and slept[0] == pytest.approx(21.0, abs=1.0), \
        "consecutive TTS calls must be spaced out for the free tier"


def test_zero_interval_disables_throttling(fake_api, tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(tts.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 0.0)
    tts.render_line("One.", "Kore", tmp_path / "1.wav")
    assert slept == [], "paid tier should not be throttled"


def test_rate_limit_is_retried_then_succeeds(fake_api, tmp_path, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    fake_api.fail_times = 2

    out = tts.render_line("Retry me.", "Kore", tmp_path / "a.wav")
    assert out.exists()
    assert len(fake_api.calls) == 3, "should have retried twice before succeeding"


def test_persistent_rate_limit_raises_a_clear_error(fake_api, tmp_path, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    monkeypatch.setattr(tts.config, "TTS_MAX_RETRIES", 3)
    fake_api.fail_times = 99

    with pytest.raises(RuntimeError, match="TTS failed after"):
        tts.render_line("Nope.", "Kore", tmp_path / "a.wav")
    assert len(fake_api.calls) == 3


class _Unavailable(Exception):
    def __str__(self) -> str:
        return "503 UNAVAILABLE. This model is currently experiencing high demand."


def test_transient_503_is_retried(fake_api, tmp_path, monkeypatch):
    """The TTS model returns 503 under load; that is temporary, not fatal."""
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    state = {"n": 0}

    def flaky(**kw):
        fake_api.calls.append(kw)
        state["n"] += 1
        if state["n"] <= 2:
            raise _Unavailable()
        return _FakeResponse()

    fake_api.generate_content = flaky
    out = tts.render_line("Hi.", "Kore", tmp_path / "a.wav")
    assert out.exists()
    assert len(fake_api.calls) == 3


def test_backoff_grows_and_is_bounded(fake_api, tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(tts.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(tts.config, "TTS_MAX_RETRIES", 4)
    fake_api.fail_times = 99

    with pytest.raises(RuntimeError):
        tts.render_line("Nope.", "Kore", tmp_path / "a.wav")

    assert len(slept) >= 3
    # Strictly increasing backoff, never a zero-delay hot loop, always capped.
    assert all(a < b for a, b in zip(slept, slept[1:])), f"backoff not growing: {slept}"
    assert all(0 < s <= 61 for s in slept), f"backoff out of bounds: {slept}"


def test_non_rate_limit_errors_are_not_retried(fake_api, tmp_path, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)

    def boom(**kw):
        fake_api.calls.append(kw)
        raise ValueError("invalid voice name")

    fake_api.generate_content = boom
    with pytest.raises(ValueError, match="invalid voice"):
        tts.render_line("Hi.", "NotAVoice", tmp_path / "a.wav")
    assert len(fake_api.calls) == 1, "a hard error must fail fast, not burn retries"


def test_multiple_keys_use_independent_round_robin_lanes(tmp_path, monkeypatch):
    created = {}

    def make_client(api_key):
        models = FakeModels()
        created[api_key] = models
        return type("Client", (), {"models": models})()

    monkeypatch.setattr(tts.config, "GEMINI_API_KEYS", ["key-a", "key-b", "key-c"])
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(tts.genai, "Client", make_client)
    monkeypatch.setattr(tts, "_lanes_signature", ())
    monkeypatch.setattr(tts, "_next_lane", 0)

    for i in range(3):
        tts.render_line(f"Line {i}", "Kore", tmp_path / f"{i}.wav")

    assert set(created) == {"key-a", "key-b", "key-c"}
    assert all(len(models.calls) == 1 for models in created.values())


def test_invalid_key_is_disabled_and_another_key_takes_over(tmp_path, monkeypatch):
    class InvalidModels(FakeModels):
        def generate_content(self, **kw):
            self.calls.append(kw)
            raise RuntimeError("401 UNAUTHENTICATED: API_KEY_INVALID")

    clients = {
        "bad-key": type("Client", (), {"models": InvalidModels()})(),
        "good-key": type("Client", (), {"models": FakeModels()})(),
    }
    monkeypatch.setattr(tts.config, "GEMINI_API_KEYS", ["bad-key", "good-key"])
    monkeypatch.setattr(tts.config, "TTS_MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(tts.genai, "Client", lambda api_key: clients[api_key])
    monkeypatch.setattr(tts, "_lanes_signature", ())
    monkeypatch.setattr(tts, "_next_lane", 0)

    out = tts.render_line("Keep going.", "Kore", tmp_path / "fallback.wav")

    assert out.exists()
    assert len(clients["bad-key"].models.calls) == 1
    assert len(clients["good-key"].models.calls) == 1
