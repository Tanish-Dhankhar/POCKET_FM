"""Focused coverage for the fast, no-TTS episode remix path."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import api_store, episode_service, store
from app.main import app


class _Handle:
    def __init__(self) -> None:
        self.steps: list[str] = []
        self.progress_updates: list[tuple[int, int, str]] = []

    def step(self, name: str, message: str = "") -> None:
        self.steps.append(name)

    def progress(self, done: int, total: int, message: str = "") -> None:
        self.progress_updates.append((done, total, message))

    def cancelled(self) -> bool:
        return False


def _ready_episode(offline, series_id: str = "remix-test") -> tuple[str, list[str]]:
    store.save_idea(series_id, "A tense conversation in a dark hospital.")
    store.save_blueprint(series_id, {
        "logline": "A nurse hears a voice from an empty room.",
        "story_world": "A hospital at night.",
        "main_storyline": "Maya investigates the impossible voice.",
        "tone": "tense",
        "theme": "grief",
        "characters": [],
    }, meta={"genre": "thriller", "setting": "hospital", "language": "English"})
    store.save_index(series_id, title="Room 4B", stage="episode_ready")
    store.save_episode_outline(series_id, {"number": 1, "title": "The Voice"})

    lines = [
        {"speaker": "Maya", "text": "Did you hear that?"},
        {"speaker": "Benji", "text": "Hear what?"},
        {"speaker": "Maya", "text": "Someone said my name."},
    ]
    store.save_episode_script(series_id, 1, lines)

    line_files = []
    for index, line in enumerate(lines):
        path = store.lines_dir(series_id, 1) / f"{index:04d}.wav"
        offline["tts"](line["text"], "Charon", path)
        line_files.append(str(path))
    voices = store.episode_dir(series_id, 1) / "ep01_voices.wav"
    offline["tts"]("Existing combined dialogue track", "Charon", voices)
    store.save_episode_audio(series_id, 1, {
        "voices": str(voices),
        "offsets": [0, 600, 1200],
        "total_ms": 1800,
        "line_files": line_files,
        "segments": [],
        "stale": False,
    })
    return series_id, line_files


def test_remix_uses_existing_audio_and_calls_only_design_then_mix(offline, monkeypatch):
    series_id, line_files = _ready_episode(offline)
    tts_calls_before = list(offline["tts"].rendered)
    calls: list[tuple[str, str | int]] = []
    plan = {"music": [{"mood": "tense"}], "sfx": []}

    def design(state, number):
        calls.append(("design", state["feedback"]))
        assert state["audio_manifest"]["1"]["line_files"] == line_files
        return plan

    def mix(state, number):
        calls.append(("mix", number))
        assert state["sound_plans"]["1"] == plan
        info = dict(state["audio_manifest"]["1"])
        info["final"] = info["voices"]
        return info

    def forbidden(*args, **kwargs):
        raise AssertionError("remix must not generate a script or call TTS")

    monkeypatch.setattr(episode_service.audio_nodes, "design_episode_sound", design)
    monkeypatch.setattr(episode_service.audio_nodes, "mix_episode", mix)
    monkeypatch.setattr(episode_service.audio_nodes, "render_episode_audio", forbidden)
    monkeypatch.setattr(episode_service.text_nodes, "gen_script_for_episode", forbidden)

    handle = _Handle()
    result = episode_service.remix_episode(
        series_id, 1, "  Duck music deeply under dialogue.  ", handle)

    assert calls == [
        ("design", "Duck music deeply under dialogue."),
        ("mix", 1),
    ]
    assert handle.steps == ["sound", "mix"]
    assert offline["tts"].rendered == tts_calls_before
    assert result["status"] == "ready"
    persisted = store.load_episode(series_id, 1)["audio"]
    assert persisted["line_files"] == line_files
    assert persisted["remix_revision"]


def test_remix_endpoint_accepts_an_instruction_and_rejects_blank_input(monkeypatch):
    captured = {}

    monkeypatch.setattr(api_store, "_require", lambda series_id: None)
    monkeypatch.setattr(api_store.store, "episode_numbers", lambda series_id: [1])

    def start(series_id, number, instruction):
        captured.update(series_id=series_id, number=number, instruction=instruction)
        return {"id": "remix-job", "state": "queued"}

    monkeypatch.setattr(api_store.episode_service, "start_episode_remix_job", start)
    client = TestClient(app)

    response = client.post(
        "/studio/series/demo/episodes/1/remix",
        json={"instruction": "  Keep effects sparse.  "},
    )
    assert response.status_code == 202
    assert response.json()["id"] == "remix-job"
    assert captured == {
        "series_id": "demo", "number": 1, "instruction": "Keep effects sparse.",
    }

    blank = client.post(
        "/studio/series/demo/episodes/1/remix", json={"instruction": "   "})
    assert blank.status_code == 422


def test_generation_finishes_with_the_automatic_cinematic_stage(offline, monkeypatch):
    series_id, _ = _ready_episode(offline, "automatic-cinematic")
    existing_audio = store.load_episode(series_id, 1)["audio"]
    calls: list[str] = []

    def evaluate(sid, number):
        calls.append("evaluate")
        return {"points": []}

    def render(state, number, progress=None):
        calls.append("voices")
        return existing_audio

    def direct(state, number):
        calls.append("direct")
        return {"dialogue": [], "music": [], "sfx": [], "ambience": []}

    def mix(state, number):
        calls.append("mix")
        return {**existing_audio, "final": existing_audio["voices"]}

    monkeypatch.setattr(episode_service.story_service, "evaluate_episode", evaluate)
    monkeypatch.setattr(episode_service.audio_nodes, "render_episode_audio", render)
    monkeypatch.setattr(episode_service.audio_nodes, "design_episode_sound", direct)
    monkeypatch.setattr(episode_service.audio_nodes, "mix_episode", mix)

    handle = _Handle()
    episode_service.generate_episode(series_id, 1, handle)

    assert episode_service.STEPS == ["script", "evaluate", "voices", "cinematic"]
    assert handle.steps == ["script", "evaluate", "voices", "cinematic"]
    assert calls == ["evaluate", "voices", "direct", "mix"]
    assert handle.progress_updates[-2:] == [
        (1, 2, "Rendering and mastering the cinematic mix"),
        (2, 2, "Cinematic episode ready"),
    ]
