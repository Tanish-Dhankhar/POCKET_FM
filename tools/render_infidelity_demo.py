"""Build the fully cached ``The Other Key`` presentation series.

The season blueprint and first episode are deliberately fixed for a dependable
demo. Artwork and immutable TTS takes are generated once; every timing, overlap,
cut, gain move, score duck, effect, and silence is then produced locally by the
cinematic editor in ``render_emotional_fight_demo``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from app import assets, audio_engine, config, image_service, images, store
from tools import render_emotional_fight_demo as editor


SERIES_ID = "the-other-key-demo"
EPISODE_NUMBER = 1
TITLE = "The Other Key"


def _line(index: int, speaker: str, text: str,
          emotion: str | None = None) -> dict[str, Any]:
    return {
        "id": f"line-{index + 1:04d}",
        "speaker": speaker,
        "emotion": emotion,
        "text": text,
    }


SCRIPT_ROWS: list[tuple[str, str, str | None]] = [
    ("Maya", "Seven years, and you still buy the wine I hate.", "Amused"),
    ("Daniel", "Seven years, and you still drink it to spare my feelings.", "Tender"),
    ("Maya", "Your coat is dripping on the anniversary gift.", "Calm"),
    ("Daniel", "Leave it. Sit down. I made the terrible pasta you like.", "Tender"),
    ("Maya", "I was looking for the corkscrew. This fell out of your pocket.", "Cold"),
    ("Daniel", "Give me that key, Maya.", "Fear"),
    ("Maya", "Hotel Marlowe. Room six-fourteen. Last Thursday.", "Cold"),
    ("Daniel", "It is not what you think.", "Nervous"),
    ("Celeste", "You promised tonight was the last lie. Tell your wife, or I will.", "Pleading"),
    ("Maya", "Tell me who Celeste is.", "Trembling"),
    ("Daniel", "Someone from the firm.", "Nervous"),
    ("Maya", "People from work do not call your marriage a lie.", "Cold"),
    ("Daniel", "She is upset. You heard half a message.", "Pleading"),
    ("Maya", "Then play the other half.", "Determined"),
    ("Daniel", "Maya, please put the phone down.", "Pleading"),
    ("Maya", "How long?", "Serious"),
    ("Daniel", "Let me explain how it started.", "Pleading"),
    ("Maya", "A number, Daniel. How long have you been sleeping with her?", "Anger"),
    ("Daniel", "It has been six months.", "Sad"),
    ("Maya", "Six months means my birthday, your mother's surgery, and every Thursday you worked late.", "Trembling"),
    ("Daniel", "I did work late some of those nights.", "Nervous"),
    ("Maya", "Do not make me audit the truth one evening at a time.", "Anger"),
    ("Daniel", "I was going to end it.", "Pleading"),
    ("Maya", "You came home from her hotel and kissed me.", "Sad"),
    ("Daniel", "I hated myself every time.", "Sad"),
    ("Maya", "That did not protect me. It only made you the saddest person in your own betrayal.", "Cold"),
    ("Daniel", "I know what I did.", "Serious"),
    ("Maya", "No. You know the part you can confess without looking at me.", "Anger"),
    ("Daniel", "I was lonely, and we had stopped talking.", "Pleading"),
    ("Maya", "We were grieving. I was in the next room, grieving too.", "Trembling"),
    ("Daniel", "Every conversation became the clinic, the injections, the bills.", "Anger"),
    ("Maya", "Because we were trying to have a child.", "Pleading"),
    ("Daniel", "I felt like a project that kept failing.", "Sad"),
    ("Maya", "So you found someone who did not know you well enough to be disappointed.", "Cold"),
    ("Daniel", "Celeste listened when I could not speak to you.", "Serious"),
    ("Maya", "I listened until you trained me not to trust what I heard.", "Trembling"),
    ("Daniel", "I never wanted you to feel crazy.", "Pleading"),
    ("Maya", "You changed your passcode and told me grief made me suspicious.", "Anger"),
    ("Daniel", "Because you searched everything I owned.", "Anger"),
    ("Maya", "Tonight, a hotel key answered me before you did.", "Cold"),
    ("Daniel", "I am standing here telling you the truth now.", "Anger"),
    ("Maya", "Only because her voice arrived before your next lie.", "Anger"),
    ("Daniel", "I said I am sorry. What else can I say?", "Anger"),
    ("Maya", "Say where you were when I did the transfer alone.", "Determined"),
    ("Daniel", "Do not drag that night into this.", "Anger"),
    ("Maya", "You said the bridge site flooded. Were you with her?", "Panic"),
    ("Daniel", "Maya, stop asking me that.", "Anger"),
    ("Maya", "Were you with her while I sat in that clinic?", "Pleading"),
    ("Daniel", "Yes. I was with her.", "Sad"),
    ("Maya", "I called you eleven times.", "Trembling"),
    ("Daniel", "I saw the calls. I froze.", "Sad"),
    ("Maya", "I apologized for needing you. I actually apologized.", "Sad"),
    ("Daniel", "I cannot undo that night.", "Pleading"),
    ("Maya", "You can stop calling it one night.", "Anger"),
    ("Daniel", "And you can stop turning every sentence into a verdict.", "Anger"),
    ("Maya", "A verdict needs doubt. You just confessed.", "Cold"),
    ("Daniel", "I am still your husband, not a monster in a courtroom.", "Anger"),
    ("Maya", "My husband held my hand this morning with her hotel key in his pocket.", "Trembling"),
    ("Maya", "You watched me inject hormones alone, watched me blame my body, and if you would just let me finish asking whether any part of our marriage was real—", "Pleading"),
    ("Daniel", "ENOUGH!", "Shouting"),
    ("Daniel", "I did not shout because you are wrong. I shouted because there is more.", "Trembling"),
    ("Maya", "What more could there possibly be?", "Cold"),
    ("Daniel", "I moved money from the treatment account.", "Sad"),
    ("Maya", "Tell me exactly how much.", "Trembling"),
    ("Daniel", "All of it. I used it for the deposit on her apartment.", "Sad"),
    ("Maya", "You spent our chance at a child on a home for her.", "Cold"),
]
# Keep the complete written scene above as the season-writing source, but the
# presentation cut is a purpose-written 20-line cold open. The affair is proven
# immediately and the signature interruption lands inside the first minute.
PRESENTATION_ROWS: list[tuple[str, str, str | None]] = [
    ("Maya", "Don't open the wine.", "Cold"),
    ("Daniel", "Why? It is our anniversary.", "Nervous"),
    ("Maya", "I found this in your coat.", "Trembling"),
    ("Daniel", "Maya, give me the key.", "Fear"),
    ("Maya", "Hotel Marlowe. Room six-fourteen. Every Thursday.", "Cold"),
    ("Daniel", "It is a client suite.", "Nervous"),
    ("Celeste", "You promised you would tell her tonight. I cannot keep being your Thursday.", "Pleading"),
    ("Maya", "Was that your client?", "Cold"),
    ("Daniel", "I can explain what happened.", "Pleading"),
    ("Maya", "Then say her name.", "Determined"),
    ("Daniel", "Her name is Celeste.", "Sad"),
    ("Maya", "Tell me how long.", "Trembling"),
    ("Daniel", "It has been six months.", "Sad"),
    ("Maya", "Six months, while I was taking those injections alone?", "Panic"),
    ("Daniel", "It was never about you.", "Pleading"),
    ("Maya", "That is the coward's line. You made it about me every time you called me paranoid.", "Anger"),
    ("Daniel", "I was going to end it tonight.", "Anger"),
    ("Maya", "After dinner? After I thanked you for staying?", "Trembling"),
    ("Maya", "You watched me question my own mind while you came home from her bed, and if you would let me finish for once, tell me whether any part of us was—", "Pleading"),
    ("Daniel", "ENOUGH!", "Shouting"),
]
SCRIPT = [_line(i, *row) for i, row in enumerate(PRESENTATION_ROWS)]
INTERRUPTED_LINE = 18
SHOUT_LINE = 19
assert len(SCRIPT) == 20
assert SCRIPT[SHOUT_LINE]["text"] == "ENOUGH!"


EPISODES = [
    {
        "number": 1, "title": "Room 614",
        "summary": "During their seventh-anniversary dinner, Maya finds a hotel key in Daniel's coat and hears Celeste's voice note. Daniel admits a six-month affair; when Maya names the gaslighting, he interrupts her with a shout that kills every sound in the room.",
        "main_events": ["Anniversary dinner", "Hotel key discovered", "Celeste's voice note", "Affair confession", "Argument hard-cuts to silence"],
        "emotional_focus": "Shock becoming moral clarity",
        "cliffhanger": "Daniel's ENOUGH cuts Maya off mid-sentence and the episode falls into absolute silence.",
        "status": "ready",
    },
    {
        "number": 2, "title": "The Ledger",
        "summary": "Maya traces the missing money and discovers Daniel built the deception through small transfers labeled as clinic fees. She freezes the remaining joint accounts before he can explain them away.",
        "main_events": ["Bank audit", "False clinic labels", "Accounts frozen", "Daniel locked out"],
        "emotional_focus": "Control returning through evidence",
        "cliffhanger": "One transfer bears Celeste's signature, proving she knew the money belonged to Maya.",
        "status": "planned",
    },
    {
        "number": 3, "title": "Her Version",
        "summary": "Maya meets Celeste expecting an enemy and learns Daniel told Celeste he had been separated for a year. Celeste provides messages showing he manipulated both women with different stories.",
        "main_events": ["Maya contacts Celeste", "Two timelines compared", "Daniel's lies aligned", "Unexpected alliance"],
        "emotional_focus": "Rage complicated by empathy",
        "cliffhanger": "Celeste reveals Daniel planned to announce the separation using a letter written in Maya's name.",
        "status": "planned",
    },
    {
        "number": 4, "title": "Drafts",
        "summary": "The forged separation draft forces Daniel to confront how often he rehearsed consequences without accepting them. Maya listens to an old therapy recording and hears the exact moment she stopped believing herself.",
        "main_events": ["Forged letter recovered", "Therapy audio replayed", "Daniel challenged", "Maya names the gaslighting"],
        "emotional_focus": "Memory becoming testimony",
        "cliffhanger": "The therapist's recording mentions a second hidden account Maya has never seen.",
        "status": "planned",
    },
    {
        "number": 5, "title": "Thursday",
        "summary": "Maya reconstructs every Thursday of the affair and discovers Daniel's mother repeatedly covered for him. The family dinner that follows becomes a quiet confrontation about loyalty and complicity.",
        "main_events": ["Calendar reconstruction", "Family cover story", "Dinner confrontation", "Daniel's mother admits the truth"],
        "emotional_focus": "Betrayal widening beyond the marriage",
        "cliffhanger": "Daniel's mother says the second account was created before the affair began.",
        "status": "planned",
    },
    {
        "number": 6, "title": "Before Celeste",
        "summary": "The hidden account reveals Daniel had been preparing an exit long before meeting Celeste. He finally admits the affair was not the cause of the marriage's collapse but the place he hid from making an honest decision.",
        "main_events": ["Hidden account opened", "Pre-affair timeline", "Daniel's full confession", "Celeste ends contact"],
        "emotional_focus": "The relief and cruelty of complete truth",
        "cliffhanger": "Maya finds the account beneficiary is still listed as her, not Celeste.",
        "status": "planned",
    },
    {
        "number": 7, "title": "Terms",
        "summary": "Maya writes separation terms centered on restitution rather than revenge. Daniel must sell the apartment, repay the treatment fund, and tell both families the truth without asking either woman to protect him.",
        "main_events": ["Separation drafted", "Restitution terms", "Public accountability", "Apartment listed"],
        "emotional_focus": "Boundaries replacing retaliation",
        "cliffhanger": "Daniel signs, then leaves Maya the unopened anniversary gift.",
        "status": "planned",
    },
    {
        "number": 8, "title": "The Key She Keeps",
        "summary": "Months later, Maya uses the returned money to begin a life she chose rather than resume the treatment they planned. Daniel offers an apology without a request for reunion, and Maya closes the marriage without erasing what was real.",
        "main_events": ["Restitution completed", "Maya chooses a new home", "Final honest apology", "Marriage closed without reconciliation"],
        "emotional_focus": "Grief resolving into self-trust",
        "cliffhanger": "Maya places the key to her new apartment on her own ring and walks inside alone.",
        "status": "planned",
    },
]


CHARACTERS = [
    {
        "name": "Maya", "role": "Protagonist", "gender": "Woman",
        "description": "A forensic accountant whose instinct for patterns becomes the tool that restores her self-trust.",
        "personality": "Observant, dryly funny, loyal, exacting under pressure, emotionally direct once denial breaks.",
        "relationships": ["Daniel: husband of seven years", "Celeste: the woman Daniel deceived alongside her"],
        "backstory": "Maya and Daniel married young and spent two difficult years pursuing fertility treatment after a miscarriage.",
        "physical_persona": "South Asian woman in her early thirties; expressive dark eyes, shoulder-length black hair, restrained contemporary clothing, composure visibly cracking but never glamorized.",
        "vocal_signature": "Measured contralto; precision sharpens when hurt and breath catches only when control finally fails.",
        "vocal_direction": "Intimate adult woman; grounded, intelligent, grief held close until the later crying beat.",
        "voice_id": "Achernar", "is_narrator": False,
    },
    {
        "name": "Daniel", "role": "Husband / antagonist", "gender": "Man",
        "description": "An architect who avoids conflict until avoidance becomes a system of financial and emotional betrayal.",
        "personality": "Charming, conflict-averse, self-pitying under pressure, capable of accountability only after every escape closes.",
        "relationships": ["Maya: wife", "Celeste: colleague and affair partner"],
        "backstory": "Daniel built a respectable marriage and career while quietly treating indecision as innocence.",
        "physical_persona": "South Asian man in his mid-thirties; tired tailored shirt, rain-dark coat, carefully controlled posture that collapses during confession.",
        "vocal_signature": "Warm baritone that becomes clipped and defensive; the single shout should be frightening because it is rare.",
        "vocal_direction": "Adult man; naturalistic remorse and defensiveness, one explosive ENOUGH, then shaken quiet.",
        "voice_id": "Algenib", "is_narrator": False,
    },
    {
        "name": "Celeste", "role": "Catalyst / reluctant ally", "gender": "Woman",
        "description": "Daniel's colleague, initially framed as the other woman before evidence shows how thoroughly he deceived her too.",
        "personality": "Direct, impatient with ambiguity, ashamed but unwilling to absorb Daniel's blame.",
        "relationships": ["Daniel: colleague and former lover", "Maya: adversary who becomes a truth-sharing ally"],
        "backstory": "Celeste believed Daniel had been separated for a year and learns the marriage was active only after the anniversary voice note.",
        "physical_persona": "Woman in her early thirties; cropped dark curls, practical workwear, alert gaze, photographed without seduction or villain coding.",
        "vocal_signature": "Clear mid-range voice; concise, unsentimental, privately vulnerable.",
        "vocal_direction": "Adult woman; voice-note intimacy, tired resolve rather than melodrama.",
        "voice_id": "Gacrux", "is_narrator": False,
    },
]


ANALYSIS = {
    "strengths": [
        "The affair reveal arrives through concrete audio evidence within the opening minute.",
        "Financial deception turns a familiar infidelity premise into a season-scale mystery with measurable consequences.",
        "Maya and Celeste are allowed to compare evidence instead of being reduced to romantic rivals.",
    ],
    "weaknesses": [
        "A contained two-person premiere depends heavily on performance and precise escalation.",
        "Daniel can become dramatically flat if later episodes confuse explanation with redemption.",
    ],
    "opportunities": [
        "Bank alerts, voice notes, calendars, therapy recordings, and keys give each episode a distinct audio motif.",
        "The story can examine gaslighting and restitution without forcing reconciliation.",
        "Celeste's evidence creates reversals that remain emotionally plausible.",
    ],
    "threats": [
        "Soap-opera escalation would weaken the realistic opening.",
        "Over-scoring the fight would make the performances feel manipulated rather than immediate.",
    ],
    "genre_description": "A grounded relationship drama with mystery structure: each piece of evidence changes who held knowledge, money, and choice.",
    "genre_tags": ["Relationship Drama", "Domestic Mystery", "Romance", "Psychological"],
    "genre_distribution": {"action": 1, "drama": 50, "comedy": 1, "sci_fi": 0, "horror": 1, "thriller": 22, "romance": 25},
    "theme_description": "The season separates love from entitlement and asks what honest restitution looks like after trust becomes a shared financial loss.",
    "themes": [
        {"label": "Betrayal and Truth", "percentage": 35},
        {"label": "Self-Trust", "percentage": 30},
        {"label": "Accountability", "percentage": 20},
        {"label": "Letting Go", "percentage": 15},
    ],
}


def _fingerprint() -> str:
    payload = json.dumps(SCRIPT, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _configure_editor() -> None:
    # The presentation build must finish even when the Gemini preview endpoint
    # repeatedly returns an empty candidate for a valid line.
    config.TTS_OPENAI_FALLBACK_ENABLED = True
    config.TTS_MAX_RETRIES = 1
    editor.SERIES_ID = SERIES_ID
    editor.EPISODE_NUMBER = EPISODE_NUMBER
    editor.INTERRUPTED_LINE = INTERRUPTED_LINE
    editor.SHOUT_LINE = SHOUT_LINE
    editor.SCRIPT = SCRIPT
    editor.EPISODES = EPISODES
    editor.SCRIPT_FINGERPRINT = _fingerprint()


def _mix_presentation_cut(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create the continuous 50-line cut; only ENOUGH is followed by silence."""
    items = [
        {
            "line_index": int(segment["line_index"]),
            "line_id": segment["line_id"],
            "speaker": segment["speaker"],
            "path": path,
        }
        for segment, path in zip(manifest["segments"], manifest["line_files"])
    ]
    source_durations = [int(value) for value in manifest["line_durations_ms"]]
    edits: list[dict[str, Any]] = []
    slow = {"Sad", "Trembling", "Pleading", "Fear"}
    hot = {"Anger", "Panic", "Shouting"}
    for index, line in enumerate(SCRIPT):
        emotion = line.get("emotion")
        rate = 0.94 if emotion in slow else (1.05 if emotion in hot else 1.0)
        gain = -1.8 if emotion in slow else (1.2 if emotion in hot else 0.0)
        edits.append({
            "line": index,
            "pause_before_ms": 0,
            "pause_after_ms": 0,
            "rate": rate,
            "gain_db": gain,
        })

    # Increasing crosstalk makes the argument feel less rehearsed while every
    # non-overlapped handoff remains sample-contiguous (zero positive gap).
    for line, overlap in ((3, 80), (5, 110), (7, 140), (8, 170),
                          (9, 200), (11, 180), (12, 220), (15, 280),
                          (16, 320), (18, 380)):
        edits[line]["overlap_previous_ms"] = overlap
    trim_tail = max(900, min(1_600, round(source_durations[INTERRUPTED_LINE] * 0.10)))
    edits[INTERRUPTED_LINE].update({
        "rate": 0.92, "gain_db": 0.8,
        "trim_tail_ms": trim_tail, "fade_out_ms": 8,
    })
    edits[SHOUT_LINE].update({
        "overlap_previous_ms": 260,
        "interrupt": True,
        "rate": 1.04,
        "gain_db": 4.5,
        "fade_in_ms": 4,
        "pause_after_ms": 2_500,
    })

    dialogue, segments, offsets = audio_engine.assemble_dialogue(
        items, edits, default_pause_ms=0,
    )
    # Keep the signature interruption inside the first minute without inserting
    # gaps or removing words. The editor accelerates the exchange uniformly only
    # if the source performances run long.
    shout_start = int(segments[SHOUT_LINE]["start_ms"])
    if shout_start > 57_000:
        ratio = min(1.35, shout_start / 57_000)
        for edit in edits:
            if edit["line"] != SHOUT_LINE:
                edit["rate"] = min(1.35, round(edit["rate"] * ratio, 4))
        dialogue, segments, offsets = audio_engine.assemble_dialogue(
            items, edits, default_pause_ms=0,
        )
    dialogue = editor._conform(dialogue)
    duration_ms = len(dialogue)
    episode_dir = store.episode_dir(SERIES_ID, EPISODE_NUMBER)
    shout_start = int(segments[SHOUT_LINE]["start_ms"])

    score_source = editor._conform(audio_engine.load(editor.MUSIC_PATH))
    score = audio_engine._loop_to(score_source, shout_start) - 13.0
    score = score.fade_in(min(1_800, shout_start)).fade_out(min(12, shout_start))
    dialogue_regions = audio_engine._dialogue_regions(
        segments, 0, shout_start, hold_ms=60,
    )
    score = audio_engine._apply_duck_envelope(
        score, dialogue_regions, duck_db=-8.5,
        attack_ms=35, release_ms=110,
    )
    music_stem = editor._blank(duration_ms).overlay(score, position=0)

    ambience_stem = editor._overlay_span(
        editor._blank(duration_ms), audio_engine.load(editor.ROOM_TONE_PATH),
        0, shout_start, gain_db=8.0, fade_in_ms=350, fade_out_ms=10,
    )
    sfx_stem = editor._blank(duration_ms)
    cup = editor._conform(audio_engine.load(editor.CUP_PATH))[:650].fade_out(90) - 11.0
    sfx_stem = sfx_stem.overlay(cup, position=max(0, int(segments[2]["start_ms"]) - 180))
    sniff_source = audio_engine.trim_edge_silence(audio_engine.load(editor.SNIFF_PATH), {
        "silence_threshold_dbfs": -48, "max_trim_ms": 2_000,
        "keep_ms": 20, "chunk_ms": 5,
    })
    sniff = editor._conform(sniff_source)[:1_100].fade_in(12).fade_out(90) - 5.0
    sfx_stem = sfx_stem.overlay(
        sniff, position=max(0, int(segments[17]["end_ms"]) - 320),
    )

    dialogue_path = episode_dir / "ep01_dialogue_edit.wav"
    music_path = episode_dir / "ep01_music_stem.wav"
    ambience_path = episode_dir / "ep01_ambience_stem.wav"
    sfx_path = episode_dir / "ep01_sfx_stem.wav"
    final_path = episode_dir / "ep01_final.wav"
    for track, path in (
        (dialogue, dialogue_path), (music_stem, music_path),
        (ambience_stem, ambience_path), (sfx_stem, sfx_path),
    ):
        audio_engine.export(track, path)
    final = audio_engine.mix_and_master([
        {"audio": dialogue}, {"audio": music_stem},
        {"audio": ambience_stem}, {"audio": sfx_stem},
    ], {
        "duration_ms": duration_ms,
        "headroom_db": 3.0,
        "target_dbfs": -17.5,
        "peak_ceiling_dbfs": -1.0,
    })
    audio_engine.export(final, final_path)

    pre_shout_gaps = [
        int(segments[index + 1]["start_ms"]) - int(segments[index]["end_ms"])
        for index in range(SHOUT_LINE)
    ]
    silence_start = int(segments[SHOUT_LINE]["end_ms"])
    silence_probe = final[silence_start:duration_ms]
    metrics = {
        "duration_ms": duration_ms,
        "source_dialogue_calls": len(SCRIPT),
        "continuous_handoffs": all(gap <= 0 for gap in pre_shout_gaps),
        "largest_positive_gap_ms": max(0, max(pre_shout_gaps, default=0)),
        "overlap_count": sum(1 for gap in pre_shout_gaps if gap < 0),
        "interrupted_line": INTERRUPTED_LINE + 1,
        "shout_line": SHOUT_LINE + 1,
        "shout_text": SCRIPT[SHOUT_LINE]["text"],
        "shout_start_ms": shout_start,
        "shout_overlap_ms": int(segments[SHOUT_LINE]["overlap_previous_ms"]),
        "all_beds_hard_stop_ms": shout_start,
        "absolute_silence_start_ms": silence_start,
        "absolute_silence_end_ms": duration_ms,
        "absolute_silence_ms": duration_ms - silence_start,
        "absolute_silence_dbfs": (
            None if not silence_probe or silence_probe.dBFS == float("-inf")
            else round(silence_probe.dBFS, 2)
        ),
        "final_dbfs": round(final.dBFS, 2),
        "final_peak_dbfs": round(final.max_dBFS, 2),
    }
    plan = {
        "dialogue": edits,
        "music": [{
            "title": assets.manifest()["music"]["emotional"]["title"],
            "start_ms": 0, "end_ms": shout_start,
            "gain_db": -13.0, "duck_db": -8.5,
            "hard_stop_reason": "Daniel interrupts Maya with ENOUGH",
        }],
        "ambience": [{
            "name": "room_tone", "start_ms": 0,
            "end_ms": shout_start, "gain_db": 8.0,
        }],
        "sfx": [
            {"name": "anniversary_glass_clink", "near_line": 3},
            {"name": "post_crying_sniff", "near_line": 18},
        ],
        "editor_notes": [
            "Exactly 20 spoken lines and no narrator.",
            "Every pre-climax handoff has zero positive gap; selected lines overlap automatically.",
            "Dialogue rate and gain respond to delivery emotion.",
            "Maya's line 19 is physically trimmed; Daniel's ENOUGH starts before it ends.",
            "Music is ducked under speech and hard-cuts with ambience and SFX at ENOUGH.",
            "The episode ends in 2.5 seconds of digital silence.",
        ],
        "metrics": metrics,
    }
    store.save_episode_sound_plan(SERIES_ID, EPISODE_NUMBER, plan)
    updated = dict(manifest)
    updated.update({
        "script_fingerprint": _fingerprint(),
        "offsets": offsets,
        "segments": segments,
        "total_ms": duration_ms,
        "edited_line_durations_ms": [int(row["duration_ms"]) for row in segments],
        "dialogue_edit": str(dialogue_path),
        "music_stem": str(music_path),
        "ambience_stem": str(ambience_path),
        "sfx_stem": str(sfx_path),
        "final": str(final_path),
        "final_sha256": editor._sha256(final_path),
        "stale": False,
        "cinematic_editor": metrics,
    })
    store.save_episode_audio(SERIES_ID, EPISODE_NUMBER, updated)
    store.save_index(SERIES_ID, stage="episode_ready", ep_count=len(EPISODES))
    return updated, plan


def _write_project() -> None:
    store.save_index(
        SERIES_ID, title=TITLE, genre="Intimate Relationship Mystery",
        include_narrator=False, ep_count=len(EPISODES), ep_minutes=1,
        revision=1, stage="scripted",
        arcs=[
            {"title": "Discovery", "episodes": "1-2", "summary": "Maya converts shock into evidence and protects what remains."},
            {"title": "Two Versions", "episodes": "3-6", "summary": "Maya and Celeste compare timelines until Daniel's complete system of deception is visible."},
            {"title": "Restitution", "episodes": "7-8", "summary": "The marriage ends through accountability rather than revenge or a false reunion."},
        ],
    )
    store.save_idea(SERIES_ID, "A wife discovers her husband's affair during their anniversary dinner and follows the evidence into a larger financial betrayal.")
    store.save_confirmations(SERIES_ID, {
        "title": TITLE, "genre": "Intimate Relationship Mystery",
        "setting": "A rain-soaked city apartment and the evidence trail beyond it",
        "include_narrator": False, "ep_count": len(EPISODES), "ep_minutes": 1,
        "genre_tags": ANALYSIS["genre_tags"], "theme_tags": ANALYSIS["themes"],
    })
    store.save_blueprint(SERIES_ID, {
        "logline": "On her seventh anniversary, a forensic accountant finds a hotel key in her husband's coat and follows one affair into a hidden architecture of money, gaslighting, and postponed choices.",
        "story_world": "Present-day urban India, beginning inside Maya and Daniel's rain-muted apartment and expanding through banks, offices, family dining rooms, and a nearly empty rented flat.",
        "main_storyline": "Maya uses the skills Daniel once admired to reconstruct his affair and recover agency over their shared future. The evidence connects Celeste, a forged separation letter, family cover stories, and a hidden account created before the affair. Rather than compete for Daniel, Maya and Celeste exchange the truths he divided between them. The season ends with financial restitution, an honest separation, and Maya choosing a new home and future without being pushed toward revenge or reconciliation.",
        "story_beats": [
            "A hotel key and voice note expose the affair.",
            "The IVF fund is revealed as the affair apartment deposit.",
            "Maya and Celeste compare incompatible versions of the marriage.",
            "Therapy recordings prove how suspicion was pathologized.",
            "Family complicity and the pre-affair account widen the betrayal.",
            "Maya defines restitution and ends the marriage on her own terms.",
        ],
        "theme": "Rebuilding self-trust after intimate betrayal",
        "tone": "Raw, intelligent, intimate, restrained",
        "theme_tags": ANALYSIS["themes"],
        "genre": "Intimate Relationship Mystery",
        "genre_tags": ANALYSIS["genre_tags"],
        "setting": "A rain-soaked city apartment and the evidence trail beyond it",
        "language": "English",
        "characters": CHARACTERS,
    })
    store.save_story_analysis(SERIES_ID, ANALYSIS)
    store.save_voice_cast(SERIES_ID, {"Maya": "Achernar", "Daniel": "Algenib", "Celeste": "Gacrux"})
    for outline in EPISODES:
        store.save_episode_outline(SERIES_ID, outline)
    store.save_episode_script(SERIES_ID, EPISODE_NUMBER, SCRIPT)
    store.save_episode_evaluation(SERIES_ID, EPISODE_NUMBER, {
        "points": [
            {"category": "Hook", "assessment": "The hotel key and voice note make the affair undeniable inside the first minute.", "suggestion": "Keep the dinner opening warm enough that the tonal rupture is felt."},
            {"category": "Escalation", "assessment": "Each confession answers one question while exposing a more damaging choice.", "suggestion": "Protect the planned pauses and prevent crosstalk from obscuring new facts."},
            {"category": "Performance", "assessment": "Maya's crying emerges from remembered isolation rather than a generic sob loop.", "suggestion": "Use only the single post-crying sniff and let breath carry the rest."},
            {"category": "Signature beat", "assessment": "The interrupted plea, ENOUGH, and digital silence create a clean demo moment.", "suggestion": "Keep every non-voice stem silent until Daniel returns in a shaken voice."},
        ],
        "stale": False,
    })
    store.save_emotional_curve(SERIES_ID, {
        "emotion_1_label": "Betrayal", "emotion_2_label": "Agency", "emotion_3_label": "Grief",
        "dominant_emotion": "Betrayal",
        "summary": "Betrayal peaks early, then changes form as evidence expands; grief recedes only as Maya's agency becomes actionable.",
        "points": [
            {"episode": 1, "emotion_1": 96, "emotion_2": 15, "emotion_3": 88},
            {"episode": 2, "emotion_1": 86, "emotion_2": 42, "emotion_3": 78},
            {"episode": 3, "emotion_1": 82, "emotion_2": 55, "emotion_3": 68},
            {"episode": 4, "emotion_1": 78, "emotion_2": 61, "emotion_3": 74},
            {"episode": 5, "emotion_1": 90, "emotion_2": 66, "emotion_3": 63},
            {"episode": 6, "emotion_1": 72, "emotion_2": 75, "emotion_3": 58},
            {"episode": 7, "emotion_1": 45, "emotion_2": 91, "emotion_3": 50},
            {"episode": 8, "emotion_1": 25, "emotion_2": 98, "emotion_3": 36},
        ],
    }, EPISODES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-voices", action="store_true")
    parser.add_argument("--skip-artwork", action="store_true")
    parser.add_argument("--sync-databricks", action="store_true")
    args = parser.parse_args()

    if not args.sync_databricks:
        config.DATABRICKS_ENABLED = False
    _configure_editor()
    _write_project()
    artwork = (
        {"skipped": "requested"}
        if args.skip_artwork else image_service.ensure_series_images(SERIES_ID)
    )
    manifest, generated = editor._render_voices(args.force_voices)
    updated, plan = _mix_presentation_cut(manifest)
    result = {
        "series_id": SERIES_ID,
        "series_title": TITLE,
        "planned_episodes": len(EPISODES),
        "episode": EPISODE_NUMBER,
        "voices_generated_now": generated,
        "line_count": len(SCRIPT),
        "images_enabled": images.enabled(),
        "artwork": artwork,
        "final": updated["final"],
        "metrics": plan["metrics"],
    }
    print("RESULT=" + json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
