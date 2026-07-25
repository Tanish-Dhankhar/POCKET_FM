"""Shared fixtures: fake LLM + fake TTS so the whole pipeline runs offline.

The fakes are schema-aware — they return a valid instance of whatever Pydantic
schema a node asks for, so tests exercise the real graph wiring, the real
enforcement logic and the real audio engine without touching the network.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from app import config, schemas

# Tests must stay hermetic regardless of the developer's local .env: force the
# Databricks dual-write mirror off so `store.save_*` calls throughout this
# suite never attempt real network calls or write test data into a real
# workspace, even if DATABRICKS_ENABLED=true is set for the running app.
config.DATABRICKS_ENABLED = False


# --------------------------------------------------------------------------- #
# fake LLM
# --------------------------------------------------------------------------- #
def _character(name: str, role: str) -> dict:
    return {
        "name": name, "role": role, "description": f"{name} is the {role}.",
        "personality": "stubborn, warm", "relationships": [f"knows the other one"],
        "vocal_signature": "low, deliberate", "is_narrator": name == "Narrator",
    }


FAKE_SCRIPT_LINES = [
    {"type": "narration", "speaker": "Narrator",
     "text": "The corridor lights stuttered once, then held.", "sfx": [], "music": "tense"},
    {"type": "dialogue", "speaker": "Maya",
     "text": "[Whisper] Room 4B again. Every single night.", "sfx": [], "music": None},
    {"type": "dialogue", "speaker": "Benji",
     "text": "You need sleep, not a ghost story.", "sfx": [], "music": None},
    {"type": "dialogue", "speaker": "Maya",
     "text": "[Fear] Then explain the footage.", "sfx": ["door_creak"], "music": None},
    {"type": "narration", "speaker": "Narrator",
     "text": "Behind them, the door to 4B swung open on its own.", "sfx": [], "music": None},
]


class FakeLLM:
    """Schema-dispatching stand-in for llm.generate_structured."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []   # (schema name, feedback-bearing prompt)
        self.clarify_questions = 1

    def __call__(self, prompt, schema, *, thinking=None, system=None):
        self.calls.append((schema.__name__, prompt))
        return getattr(self, f"_{schema.__name__}")(prompt)

    # -- per-schema builders -------------------------------------------------
    def _ExtractResult(self, prompt):
        return schemas.ExtractResult(
            genre="supernatural thriller", theme="grief and denial",
            tone="tense, intimate", language="English",
            setting="a small county hospital, present day",
            logline="A night nurse has three nights to solve room 4B.",
            characters=[
                schemas.DetectedCharacter(name="Maya", role="protagonist",
                                          description="Night-shift nurse."),
                schemas.DetectedCharacter(name="Benji", role="skeptic",
                                          description="Security guard."),
            ],
        )

    def _ClarifyResult(self, prompt):
        qs = [
            schemas.ClarifyQuestion(
                question=f"Story decision {i + 1}: is the ghost real or psychological?",
                options=[schemas.ClarifyOption(label="A. Real", detail="Truly supernatural.", recommended=True),
                         schemas.ClarifyOption(label="B. In her head", detail="Grief-driven.")],
                allow_free_text=True,
            )
            for i in range(4)
        ]
        return schemas.ClarifyResult(questions=qs)

    def _Blueprint(self, prompt):
        return schemas.Blueprint(
            logline="Three nights, one room, one impossible patient.",
            story_world="A decaying county hospital scheduled for demolition.",
            main_storyline="Maya uncovers what the hospital buried in 4B.",
            tone="tense, intimate", theme="grief and denial",
            characters=[
                schemas.CharacterProfile(**_character("Maya", "protagonist")),
                schemas.CharacterProfile(**_character("Benji", "skeptic")),
                schemas.CharacterProfile(**_character("Narrator", "narrator")),
            ],
        )

    def _EpisodeConfigSuggestion(self, prompt):
        return schemas.EpisodeConfigSuggestion(
            recommended_ep_count=6, rationale="Three nights split into six beats.")

    def _EpisodePlan(self, prompt):
        # Honour the episode count the prompt asked for.
        count = 2
        for token in prompt.split():
            if token.isdigit():
                count = int(token)
                break
        return schemas.EpisodePlan(episodes=[
            schemas.EpisodePlanItem(
                number=i, title=f"Night {i}", summary=f"Maya returns to 4B, night {i}.",
                main_events=["She reviews the footage", "The door opens"],
                emotional_focus="dread", cliffhanger="The patient waves back.",
            ) for i in range(1, count + 1)
        ])

    def _EpisodeScript(self, prompt):
        return schemas.EpisodeScript(
            lines=[schemas.ScriptLine(**ln) for ln in FAKE_SCRIPT_LINES])

    def _VoiceCastSuggestion(self, prompt):
        return schemas.VoiceCastSuggestion(assignments=[
            schemas.VoiceAssignment(character="Maya", voice_id="Leda", reason="youthful"),
            schemas.VoiceAssignment(character="Benji", voice_id="Algenib", reason="gravelly"),
            schemas.VoiceAssignment(character="Narrator", voice_id="Charon", reason="informative"),
        ])

    def _SoundPlan(self, prompt):
        return schemas.SoundPlan(
            music=[schemas.MusicCue(start_line=0, end_line=4, mood="tense")],
            sfx=[schemas.SfxCue(line=3, name="door_creak")],
        )


# --------------------------------------------------------------------------- #
# fake TTS — writes a real, playable WAV so audio_engine is genuinely exercised
# --------------------------------------------------------------------------- #
def write_tone_wav(path: Path, ms: int = 700) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(config.TTS_SAMPLE_RATE * ms / 1000)
    frames = b"".join(struct.pack("<h", (i % 400) * 40 - 8000) for i in range(n))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(config.TTS_CHANNELS)
        wf.setsampwidth(config.TTS_SAMPLE_WIDTH)
        wf.setframerate(config.TTS_SAMPLE_RATE)
        wf.writeframes(frames)
    return path


class FakeTTS:
    """Stand-in for tts.render_line that honours the same cache contract."""

    def __init__(self) -> None:
        self.rendered: list[tuple[str, str]] = []   # (text, voice)

    def __call__(self, text, voice_id, out_path, *, cache_dir=None):
        out_path = Path(out_path)
        # Duration scales with text length so timelines look realistic.
        ms = max(400, min(4000, len(text) * 55))
        self.rendered.append((text, voice_id))
        return write_tone_wav(out_path, ms)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    llm = FakeLLM()
    # Nodes import the symbol directly, so patch it in each node module.
    monkeypatch.setattr("app.nodes.text.generate_structured", llm)
    monkeypatch.setattr("app.nodes.audio.generate_structured", llm)
    return llm


@pytest.fixture
def fake_tts(monkeypatch) -> FakeTTS:
    tts = FakeTTS()
    monkeypatch.setattr("app.nodes.audio.render_line", tts)
    return tts


@pytest.fixture
def tmp_output(monkeypatch, tmp_path) -> Path:
    """Redirect all rendered artifacts into a temp dir."""
    out = tmp_path / "output"
    monkeypatch.setattr(config, "OUTPUT_DIR", out)
    monkeypatch.setattr(config, "TTS_CACHE_DIR", out / "tts_cache")
    monkeypatch.setattr("app.nodes.audio.config.OUTPUT_DIR", out)
    return out


@pytest.fixture
def offline(fake_llm, fake_tts, tmp_output):
    """Everything stubbed: the full pipeline runs with no network and no cost."""
    return {"llm": fake_llm, "tts": fake_tts, "output": tmp_output}
