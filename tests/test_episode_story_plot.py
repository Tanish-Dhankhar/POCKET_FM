"""Episode story-plot generation and persistence."""
from __future__ import annotations

from app import store, story_service


def test_evaluation_generates_script_grounded_story_plot(offline):
    series_id = "story-plot-test"
    store.save_idea(series_id, "A nurse hears a voice from an empty room.")
    store.save_blueprint(series_id, {
        "logline": "A nurse follows an impossible voice.",
        "story_world": "A hospital at night.",
        "main_storyline": "Maya investigates room 4B and finds the truth.",
        "genre": "thriller",
        "theme": "grief",
        "characters": [],
    }, meta={"genre": "thriller", "setting": "hospital", "language": "English"})
    store.save_index(series_id, title="Room 4B", stage="scripted")
    store.save_episode_outline(series_id, {
        "number": 1,
        "title": "The Voice",
        "summary": "Maya hears her name from an empty room.",
        "main_events": ["Maya hears a voice", "Benji denies it", "The voice returns"],
        "cliffhanger": "The locked door opens.",
    })
    lines = [
        {"speaker": "Maya", "text": "Did you hear that?"},
        {"speaker": "Benji", "text": "Hear what?"},
        {"speaker": "Maya", "text": "Someone said my name."},
    ]
    store.save_episode_script(series_id, 1, lines)

    evaluation = story_service.evaluate_episode(series_id, 1)

    plot = evaluation["story_plot"]
    assert plot["structure"] == "Escalating mystery"
    assert len(plot["points"]) == 5
    assert [point["line_index"] for point in plot["points"]] == [0, 1, 2, 2, 2]
    assert all(0 <= point["intensity"] <= 100 for point in plot["points"])
    assert store.load_episode(series_id, 1)["evaluation"]["story_plot"] == plot
    assert evaluation["stale"] is False
