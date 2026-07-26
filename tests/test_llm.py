"""Unit tests for OpenAI model routing without making network calls."""
from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from app import config
import app.llm as llm


class _Result(BaseModel):
    value: str


class _Responses:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def parse(self, **kwargs):
        self.calls.append(("parse", kwargs))
        return SimpleNamespace(output_parsed=_Result(value="structured"))

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return SimpleNamespace(output_text="  free form  ")


def _fake_client(monkeypatch) -> _Responses:
    responses = _Responses()
    monkeypatch.setattr(
        llm, "_openai_client", SimpleNamespace(responses=responses)
    )
    return responses


def _enable_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "MODEL_CACHE_ENABLED", True)
    monkeypatch.setattr(config, "MODEL_CACHE_DIR", tmp_path / "model-cache")
    monkeypatch.setattr(config, "MODEL_CACHE_TTL_SEC", 3600)
    monkeypatch.setattr(config, "MODEL_CACHE_VERSION", "test-v1")


def test_high_effort_structured_work_uses_sol(monkeypatch):
    responses = _fake_client(monkeypatch)

    result = llm.generate_structured(
        "build a story", _Result, thinking=config.THINK_HIGH, system="system prompt"
    )

    kind, request = responses.calls[0]
    assert result == _Result(value="structured")
    assert kind == "parse"
    assert request["model"] == config.TEXT_MODEL_HARD
    assert request["reasoning"] == {"effort": config.THINK_HIGH}
    assert request["text_format"] is _Result
    assert request["store"] is False
    assert len(request["prompt_cache_key"]) == 64
    assert [message["role"] for message in request["input"]] == ["system", "user"]


def test_low_effort_text_work_uses_luna(monkeypatch):
    responses = _fake_client(monkeypatch)

    result = llm.generate_text("label this", thinking=config.THINK_LOW)

    kind, request = responses.calls[0]
    assert result == "free form"
    assert kind == "create"
    assert request["model"] == config.TEXT_MODEL_EASY
    assert request["reasoning"] == {"effort": config.THINK_LOW}
    assert request["store"] is False
    assert len(request["prompt_cache_key"]) == 64
    assert [message["role"] for message in request["input"]] == ["user"]


def test_explicit_task_route_controls_model_effort_and_output_cap(monkeypatch):
    responses = _fake_client(monkeypatch)

    llm.generate_structured("build it", _Result, task="blueprint")

    _, request = responses.calls[0]
    route = config.TEXT_TASKS["blueprint"]
    assert request["model"] == route["model"] == config.TEXT_MODEL_HARD
    assert request["reasoning"] == {"effort": route["effort"]}
    assert request["max_output_tokens"] == route["max_output_tokens"]
    assert request["text"] == {"verbosity": "low"}
    assert "verbosity" not in request


def test_identical_structured_request_uses_disk_cache(monkeypatch, tmp_path):
    _enable_cache(monkeypatch, tmp_path)
    responses = _fake_client(monkeypatch)

    first = llm.generate_structured("same prompt", _Result, task="blueprint")
    second = llm.generate_structured("same prompt", _Result, task="blueprint")

    assert first == second == _Result(value="structured")
    assert len(responses.calls) == 1


def test_cache_key_separates_changed_prompts(monkeypatch, tmp_path):
    _enable_cache(monkeypatch, tmp_path)
    responses = _fake_client(monkeypatch)

    llm.generate_structured("prompt one", _Result, task="blueprint")
    llm.generate_structured("prompt two", _Result, task="blueprint")

    assert len(responses.calls) == 2


def test_identical_free_text_request_uses_disk_cache(monkeypatch, tmp_path):
    _enable_cache(monkeypatch, tmp_path)
    responses = _fake_client(monkeypatch)

    assert llm.generate_text("same label") == "free form"
    assert llm.generate_text("same label") == "free form"
    assert len(responses.calls) == 1


def test_identical_transcription_uses_disk_cache(monkeypatch, tmp_path):
    _enable_cache(monkeypatch, tmp_path)

    class Models:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(text="spoken idea")

    models = Models()
    monkeypatch.setattr(llm, "_client", SimpleNamespace(models=models))

    assert llm.transcribe_audio(b"same audio", "audio/webm") == "spoken idea"
    assert llm.transcribe_audio(b"same audio", "audio/webm") == "spoken idea"
    assert models.calls == 1
