"""Graph wiring, human-in-the-loop routing and full offline pipeline runs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph.types import Command

from app import config
from app.graph import ALLOWED_EDIT_KEYS, AUTO_STAGES, CHAIN, GEN, build_graph
from app.state import STAGES, new_state


@pytest.fixture
def graph():
    """A fresh graph (own checkpointer) so tests never share threads."""
    return build_graph()


def _cfg(sid: str) -> dict:
    return {"configurable": {"thread_id": sid}}


def _stage_of(res: dict) -> str | None:
    ints = res.get("__interrupt__")
    return ints[0].value["stage"] if ints else None


def _drive(graph, sid, idea="A nurse, a ghost, three nights.", commands=None,
           stop_at=None):
    """Run the graph to completion, answering each interrupt."""
    commands = commands or {}
    seen = []
    res = graph.invoke(new_state(sid, idea), _cfg(sid))
    while (stage := _stage_of(res)) is not None:
        seen.append(stage)
        if stop_at and stage == stop_at:
            return res, seen
        cmd = commands.get(stage, {"action": "approve"})
        res = graph.invoke(Command(resume=cmd), _cfg(sid))
    return res, seen


# --------------------------------------------------------------------------- #
# static wiring
# --------------------------------------------------------------------------- #
def test_chain_matches_declared_stages():
    assert CHAIN == STAGES[:-1], "graph CHAIN and state.STAGES have drifted apart"
    assert STAGES[-1] == "deliver"


def test_every_chain_stage_has_a_generator():
    assert set(CHAIN) == set(GEN)


def test_auto_stages_have_no_human_gate():
    assert AUTO_STAGES == {"audio", "mix"}


def test_allowed_edit_keys_are_real_state_fields():
    from app.state import SeriesState
    unknown = ALLOWED_EDIT_KEYS - set(SeriesState.__annotations__)
    assert not unknown, f"edit keys not present in SeriesState: {unknown}"


# --------------------------------------------------------------------------- #
# interrupt behaviour
# --------------------------------------------------------------------------- #
def test_first_run_stops_at_extract_review(graph, offline):
    res = graph.invoke(new_state("s1", "A nurse and a ghost."), _cfg("s1"))
    assert _stage_of(res) == "extract"
    payload = res["__interrupt__"][0].value["payload"]
    assert payload["genre"] and payload["logline"] and payload["characters"]


def test_pipeline_visits_every_reviewable_stage_in_order(graph, offline):
    res, seen = _drive(graph, "s2", commands={
        "clarify": {"action": "submit", "data": {"clarification_answers": [{"q": 1, "a": "A"}]}},
        "ep_config": {"action": "submit", "data": {"ep_count": 1, "ep_minutes": 5}},
    })
    expected = [s for s in CHAIN if s not in AUTO_STAGES]
    assert seen == expected
    assert res["stage"] == "deliver"


def test_clarify_always_gates_with_four_questions(graph, offline):
    res, seen = _drive(graph, "s3", stop_at="clarify", commands={})
    assert seen == ["extract", "clarify"]
    payload = res["__interrupt__"][0].value["payload"]
    assert len(payload["questions"]) == 4
    assert all(len(q["options"]) == 3 for q in payload["questions"])
    assert all(sum(bool(o["recommended"]) for o in q["options"]) == 1
               for q in payload["questions"])


def test_questions_are_reused_from_the_single_bootstrap_call(graph, offline):
    res = graph.invoke(new_state("one-call", "A nurse and a ghost."), _cfg("one-call"))
    assert _stage_of(res) == "extract"
    before = len(offline["llm"].calls)

    res = graph.invoke(Command(resume={"action": "approve"}), _cfg("one-call"))

    assert _stage_of(res) == "clarify"
    assert len(offline["llm"].calls) == before
    names = [name for name, _ in offline["llm"].calls]
    assert names.count("ExtractResult") == 1
    assert names.count("ConfirmCard") == 1


def test_regenerate_reruns_generation_with_the_note(graph, offline):
    llm = offline["llm"]
    graph.invoke(new_state("s4", "A nurse and a ghost."), _cfg("s4"))
    before = len([c for c in llm.calls if c[0] == "ExtractResult"])

    res = graph.invoke(
        Command(resume={"action": "regenerate", "note": "make it much darker"}), _cfg("s4"))

    after = [c for c in llm.calls if c[0] == "ExtractResult"]
    assert len(after) == before + 1, "regenerate must re-run the generator"
    assert "make it much darker" in after[-1][1], "the note must reach the prompt"
    assert _stage_of(res) == "extract", "and it must present the new result for review"


def test_approve_does_not_rerun_generation(graph, offline):
    llm = offline["llm"]
    graph.invoke(new_state("s5", "A nurse and a ghost."), _cfg("s5"))
    before = len([c for c in llm.calls if c[0] == "ExtractResult"])
    graph.invoke(Command(resume={"action": "approve"}), _cfg("s5"))
    after = len([c for c in llm.calls if c[0] == "ExtractResult"])
    assert after == before, "resuming must not re-bill the LLM call"


def test_edit_overwrites_allowed_fields(graph, offline):
    graph.invoke(new_state("s6", "A nurse and a ghost."), _cfg("s6"))
    graph.invoke(Command(resume={
        "action": "edit",
        "data": {"genre": "cosmic horror", "tone": "bleak"},
    }), _cfg("s6"))
    values = graph.get_state(_cfg("s6")).values
    assert values["genre"] == "cosmic horror"
    assert values["tone"] == "bleak"


def test_edit_ignores_fields_outside_the_allowlist(graph, offline):
    graph.invoke(new_state("s7", "A nurse and a ghost."), _cfg("s7"))
    graph.invoke(Command(resume={
        "action": "edit",
        "data": {"genre": "noir", "series_id": "hijacked", "audio_manifest": {"1": "evil"}},
    }), _cfg("s7"))
    values = graph.get_state(_cfg("s7")).values
    assert values["genre"] == "noir"
    assert values["series_id"] == "s7", "protected field must not be writable"
    assert values["audio_manifest"] == {}


def test_approvals_accumulate_per_stage(graph, offline):
    _, _ = _drive(graph, "s8", stop_at="blueprint")
    approvals = graph.get_state(_cfg("s8")).values["approvals"]
    assert approvals.get("extract") is True


def test_ep_config_submit_drives_the_episode_count(graph, offline):
    _drive(graph, "s9", stop_at="script", commands={
        "clarify": {"action": "submit", "data": {"clarification_answers": []}},
        "ep_config": {"action": "submit", "data": {"ep_count": 3, "ep_minutes": 7}},
    })
    values = graph.get_state(_cfg("s9")).values
    assert values["ep_count"] == 3
    assert values["ep_minutes"] == 7
    assert len(values["episodes"]) == 3
    assert [e["number"] for e in values["episodes"]] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# end-to-end (offline) — artifacts on disk
# --------------------------------------------------------------------------- #
@pytest.fixture
def finished(graph, offline):
    res, _ = _drive(graph, "e2e", commands={
        "clarify": {"action": "submit", "data": {"clarification_answers": []}},
        "ep_config": {"action": "submit", "data": {"ep_count": 1, "ep_minutes": 5}},
    })
    return res, offline["output"]


def test_e2e_reaches_deliver(finished):
    res, _ = finished
    assert res["stage"] == "deliver"


def test_e2e_renders_one_wav_per_script_line(finished, offline):
    res, out = finished
    info = res["audio_manifest"]["1"]
    assert len(info["line_files"]) == len(res["scripts"]["1"])
    for p in info["line_files"]:
        assert Path(p).exists()


def test_e2e_writes_voices_and_final_mix(finished):
    res, _ = finished
    info = res["audio_manifest"]["1"]
    voices, final = Path(info["voices"]), Path(info["final"])
    assert voices.exists() and final.exists()
    assert final.stat().st_size > 10_000

    from app import audio_engine
    # The mix keeps the voice timeline's length — it overlays, never appends.
    assert len(audio_engine.load(final)) == pytest.approx(info["total_ms"], abs=50)


def test_e2e_offsets_are_monotonic_and_bounded(finished):
    res, _ = finished
    info = res["audio_manifest"]["1"]
    offsets = info["offsets"]
    assert offsets == sorted(offsets)
    assert offsets[0] == 0
    assert offsets[-1] < info["total_ms"]


def test_e2e_sound_plan_survives_enforcement(finished):
    res, _ = finished
    plan = res["sound_plans"]["1"]
    from app import assets
    for cue in plan["music"]:
        assert cue["mood"] in assets.music_moods()
        assert cue["end_ms"] > cue["start_ms"]
    for cue in plan["sfx"]:
        assert cue["name"] in assets.sfx_keys()
        assert 0 <= cue["at_ms"] <= res["audio_manifest"]["1"]["total_ms"]


def test_e2e_writes_series_json_snapshot(finished):
    res, out = finished
    root = out / "e2e"
    snapshot = root / "series.json"
    assert snapshot.exists()
    data = json.loads(snapshot.read_text())
    assert data["series_id"] == "e2e"
    # series.json is intentionally a lightweight dashboard index. The durable
    # source artifacts live in their own files so the frontend can patch them.
    assert (root / "blueprint" / "plot.json").exists()
    assert (root / "blueprint" / "characters").is_dir()
    assert (root / "episodes" / "ep01" / "script.json").exists()


def test_e2e_every_speaker_got_a_valid_voice(finished, offline):
    res, _ = finished
    used = {voice for _, voice in offline["tts"].rendered}
    assert used, "no lines were voiced"
    assert used <= set(config.VOICE_NAMES), f"invalid voice ids: {used - set(config.VOICE_NAMES)}"
