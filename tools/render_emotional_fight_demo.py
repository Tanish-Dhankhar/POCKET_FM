"""Build the cached five-minute Storywave presentation series.

The complete limited-series blueprint is hardcoded for a dependable demo. Only
Episode 1 is voiced: each immutable dialogue WAV is generated once and every
pause, overlap, interruption, cut, score move, effect, and silence is performed
after TTS. Re-running the command remixes cached takes unless ``--force-voices``
is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from app import assets, audio_engine, config, image_service, store
from app.nodes import audio as audio_nodes


SERIES_ID = "emotional-fight-demo"
EPISODE_NUMBER = 1
TARGET_DURATION_MS = 5 * 60 * 1_000
INTERRUPTED_LINE = 58
SHOUT_LINE = 59
POST_SILENCE_LINE = 60


def _script_line(index: int, speaker: str, text: str,
                 emotion: str | None = None) -> dict[str, Any]:
    return {
        "id": f"line-{index + 1:04d}",
        "speaker": speaker,
        "emotion": emotion,
        "text": text,
    }


SCRIPT_ROWS: list[tuple[str, str, str | None]] = [
    ("Maya", "You packed the blue mug.", "Trembling"),
    ("Daniel", "Maya... it's a mug.", "Cold"),
    ("Maya", "My mother gave us that.", "Sad"),
    ("Daniel", "I know.", "Cold"),
    ("Maya", "Then why is it wrapped in your shirt?", "Trembling"),
    ("Daniel", "Because it would break in the box.", "Calm"),
    ("Maya", "You said you were taking clothes.", "Serious"),
    ("Daniel", "I am taking clothes.", "Cold"),
    ("Maya", "And the record player.", "Serious"),
    ("Daniel", "It's mine.", "Cold"),
    ("Maya", "We bought it together.", "Sad"),
    ("Daniel", "You never use it.", "Cold"),
    ("Maya", "That's not the point.", "Anger"),
    ("Daniel", "Then tell me what the point is.", "Serious"),
    ("Maya", "The point is you packed a life while I was at work.", "Trembling"),
    ("Daniel", "I packed three boxes.", "Serious"),
    ("Maya", "Three boxes and the part of the apartment that sounds like you.", "Sad"),
    ("Daniel", "Please don't do that.", "Pleading"),
    ("Maya", "Do what?", "Anger"),
    ("Daniel", "Turn every object into a witness.", "Serious"),
    ("Maya", "They were here. You weren't.", "Sad"),
    ("Daniel", "I was here every night.", "Anger"),
    ("Maya", "Your whole body was shaking.", "Cold"),
    ("Daniel", "I can't do this if every answer is already wrong.", "Pleading"),
    ("Maya", "I asked one question.", "Serious"),
    ("Daniel", "No. You opened a trial.", "Anger"),
    ("Maya", "Why do you keep hiding your phone?", "Trembling"),
    ("Daniel", "I'm not hiding it.", "Nervous"),
    ("Maya", "You sleep with it under your pillow.", "Serious"),
    ("Daniel", "Because you read my messages.", "Anger"),
    ("Maya", "Once.", "Cold"),
    ("Daniel", "Once was enough.", "Anger"),
    ("Maya", "I read one name and you grabbed it out of my hand.", "Trembling"),
    ("Daniel", "Because it wasn't yours to read.", "Serious"),
    ("Maya", "Who is E?", "Fear"),
    ("Daniel", "Not tonight.", "Cold"),
    ("Maya", "You're leaving tonight.", "Anger"),
    ("Daniel", "That doesn't mean we have to destroy everything before I go.", "Pleading"),
    ("Maya", "You made the decision without me.", "Anger"),
    ("Daniel", "I made it after six months of us not speaking.", "Anger"),
    ("Maya", "I spoke. You stopped answering.", "Anger"),
    ("Daniel", "You asked the same question until I gave you the answer you wanted.", "Anger"),
    ("Maya", "I wanted the truth.", "Pleading"),
    ("Daniel", "You wanted a confession.", "Anger"),
    ("Maya", "Because innocent people don't delete messages.", "Anger"),
    ("Daniel", "You don't know what those messages were.", "Anger"),
    ("Maya", "Then show me.", "Determined"),
    ("Daniel", "No, I didn't.", "Cold"),
    ("Maya", "There it is.", "Sad"),
    ("Daniel", "There what is?", "Anger"),
    ("Maya", "That door you close and then blame me for knocking.", "Trembling"),
    ("Daniel", "You never knock, Maya. You break it down.", "Anger"),
    ("Maya", (
        "I kept waiting because I thought if I stayed calm enough, if I gave you "
        "enough space, you would remember that I was on your side. But you looked "
        "through me at breakfast, you lied about working late, and every time I "
        "tried to tell you how scared I was, you turned away."
    ), "Pleading"),
    ("Daniel", "Because every conversation became a trial!", "Anger"),
    ("Maya", "Because every conversation became an escape for you.", "Anger"),
    ("Daniel", "You don't let me finish.", "Anger"),
    ("Maya", "I have spent months waiting for you to finish disappearing.", "Trembling"),
    ("Daniel", "Maya, stop.", "Pleading"),
    ("Maya", (
        "No, because if I stop now you'll walk out and turn this into another thing "
        "we never said, and I need you to hear that I didn't need you to fix me. I "
        "needed you to tell me the truth, and if you would just let me finish this..."
    ), "Pleading"),
    ("Daniel", "ENOUGH!", "Shouting"),
    ("Daniel", "I... I didn't mean to...", "Trembling"),
    ("Maya", "You did. That's the problem.", "Sad"),
    ("Daniel", "The messages weren't from another woman.", "Serious"),
    ("Maya", "Then who were they from?", "Fear"),
    ("Daniel", "Your mother.", "Trembling"),
    ("Maya", "My mother is dead.", "Fear"),
]

SCRIPT = [
    _script_line(index, speaker, text, emotion)
    for index, (speaker, text, emotion) in enumerate(SCRIPT_ROWS)
]

SCRIPT_FINGERPRINT = hashlib.sha256(json.dumps(
    SCRIPT, sort_keys=True, ensure_ascii=False,
).encode("utf-8")).hexdigest()

MUSIC_PATH = assets.music_path("emotional")
ROOM_TONE_PATH = assets.sfx_path("room_tone")
SNIFF_PATH = assets.sfx_path("post_crying_sniff")
CUP_PATH = assets.sfx_path("tea_cup_clank")


EPISODES = [
    {
        "number": 1,
        "title": "The Blue Mug",
        "summary": (
            "While Daniel packs to leave, Maya notices the mug her late mother gave "
            "them. A controlled exchange becomes crosstalk, one devastating shout, "
            "and the revelation that Daniel has messages from a dead woman."
        ),
        "main_events": [
            "Maya discovers Daniel has packed shared objects while she was away.",
            "Suspicion around Daniel's phone turns the breakup into an interrogation.",
            "Daniel shouts ENOUGH over Maya and the entire soundscape collapses.",
            "Daniel reveals that the mysterious messages came from Maya's dead mother.",
        ],
        "emotional_arc": "disbelief -> restraint -> accusation -> rupture -> impossible revelation",
        "emotion": "Raw and escalating",
        "cliffhanger": "Daniel says the messages were from Maya's mother, who died eighteen months ago.",
    },
    {
        "number": 2,
        "title": "Eleven Unplayed Messages",
        "summary": (
            "Daniel opens a scheduled voice archive Elena recorded before her death. "
            "The first message asks Maya not to punish Daniel for keeping it secret."
        ),
        "main_events": [
            "Maya assumes the archive is fabricated and demands proof.",
            "Elena's unmistakable voice enters the series for the first time.",
            "Daniel admits he promised to release each message only when Maya was ready.",
            "The next recording is labeled with the date Daniel decided to leave.",
        ],
        "emotional_arc": "denial -> recognition -> grief -> suspicion",
        "emotion": "Haunted and intimate",
        "cliffhanger": "A message begins: 'Maya, Daniel is going to hate me for telling you this.'",
    },
    {
        "number": 3,
        "title": "The Spare Key",
        "summary": (
            "A spare key proves Daniel met Elena in secret during her final months. "
            "Maya must decide whether protection can still be a betrayal."
        ),
        "main_events": [
            "Daniel describes the first night Elena called him for help.",
            "Maya learns her mother hid the severity of her diagnosis.",
            "Priya arrives and reveals she knew about one meeting but not the recordings.",
            "Maya finds that one message has been deleted from the archive.",
        ],
        "emotional_arc": "rage -> testimony -> divided loyalty -> renewed distrust",
        "emotion": "Claustrophobic",
        "cliffhanger": "The missing file is named 'What Daniel Did.'",
    },
    {
        "number": 4,
        "title": "The Train Ticket",
        "summary": (
            "A ticket hidden in Elena's cookbook reveals that Daniel planned to move "
            "Maya away from the city after the funeral, without asking her."
        ),
        "main_events": [
            "Maya accuses Daniel of turning care into control.",
            "Daniel admits Elena encouraged the move but never ordered it.",
            "Priya exposes Maya's own secret application for a residency abroad.",
            "Both partners realize they built escape plans instead of a shared future.",
        ],
        "emotional_arc": "betrayal -> defensiveness -> symmetry -> shame",
        "emotion": "Restless and revealing",
        "cliffhanger": "Maya's acceptance letter is dated three weeks before Daniel packed.",
    },
    {
        "number": 5,
        "title": "The Empty Drawer",
        "summary": (
            "Maya and Daniel compare the futures they hid from each other while Priya "
            "searches Elena's cloud backup for the missing recording."
        ),
        "main_events": [
            "Maya admits she accepted the residency and never told Daniel.",
            "Daniel confesses he found the empty drawer and assumed she had already left.",
            "Priya recovers part of the deleted audio from a damaged backup.",
            "Elena's recovered sentence appears to accuse Daniel of lying at the hospital.",
        ],
        "emotional_arc": "confession -> empathy -> hope -> dread",
        "emotion": "Tender but unstable",
        "cliffhanger": "Elena says, 'He told you I was asleep. I wasn't.'",
    },
    {
        "number": 6,
        "title": "The Last Visit",
        "summary": (
            "Daniel finally recounts Elena's lucid final hour and why he kept Maya out "
            "of the hospital room, forcing Maya to revisit the story of her loss."
        ),
        "main_events": [
            "Daniel admits Elena asked to see him alone before Maya arrived.",
            "Elena feared Maya would abandon her future to become a full-time caretaker.",
            "Daniel obeyed Elena and told Maya she was sleeping through the final visit.",
            "Maya rejects the idea that love gave either of them the right to choose for her.",
        ],
        "emotional_arc": "testimony -> compassion -> moral injury -> separation",
        "emotion": "Devastating and quiet",
        "cliffhanger": "Priya discovers Elena recorded one final message after Daniel left.",
    },
    {
        "number": 7,
        "title": "What She Chose",
        "summary": (
            "Elena's last recording dismantles both Maya's idealized memory and Daniel's "
            "claim that secrecy was protection."
        ),
        "main_events": [
            "Elena apologizes for recruiting Daniel into her fear.",
            "She tells Maya that being protected without consent is another kind of cage.",
            "Daniel accepts that Elena's request does not excuse eighteen months of distance.",
            "Maya decides to leave for the residency, but not as an act of revenge.",
        ],
        "emotional_arc": "anticipation -> truth -> accountability -> agency",
        "emotion": "Clear-eyed and cathartic",
        "cliffhanger": "Daniel asks whether Maya wants him to unpack the blue mug.",
    },
    {
        "number": 8,
        "title": "What We Leave",
        "summary": (
            "At sunrise, Maya and Daniel finish packing without pretending honesty can "
            "restore the relationship. They choose a truthful ending over a false reunion."
        ),
        "main_events": [
            "They divide their shared objects without using them as weapons.",
            "Maya keeps the mug and gives Daniel the record player.",
            "Daniel leaves the phone and Elena's archive with Maya.",
            "They part with love, grief, and no promise that separation is temporary.",
        ],
        "emotional_arc": "aftermath -> tenderness -> release -> forward motion",
        "emotion": "Bittersweet and resolved",
        "cliffhanger": "Maya plays Elena's first message again, this time without stopping it.",
    },
]


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _conform(segment: AudioSegment, *, channels: int = 2) -> AudioSegment:
    return (segment.set_frame_rate(config.TTS_SAMPLE_RATE)
            .set_sample_width(config.TTS_SAMPLE_WIDTH)
            .set_channels(channels))


def _blank(duration_ms: int) -> AudioSegment:
    return (AudioSegment.silent(duration=duration_ms, frame_rate=config.TTS_SAMPLE_RATE)
            .set_sample_width(config.TTS_SAMPLE_WIDTH)
            .set_channels(2))


def _overlay_span(track: AudioSegment, source: AudioSegment, start_ms: int,
                  end_ms: int, *, gain_db: float, fade_in_ms: int = 0,
                  fade_out_ms: int = 0) -> AudioSegment:
    span = max(0, end_ms - start_ms)
    if span == 0:
        return track
    bed = audio_engine._loop_to(_conform(source), span) + gain_db
    if fade_in_ms:
        bed = bed.fade_in(min(span, fade_in_ms))
    if fade_out_ms:
        bed = bed.fade_out(min(span, fade_out_ms))
    return track.overlay(bed, position=start_ms)


def _write_project() -> None:
    title = "The Things We Packed"
    genre = "Intimate Mystery Drama"
    setting = "A small apartment over one rain-soaked weekend"
    store.save_index(
        SERIES_ID, title=title, genre=genre, include_narrator=False,
        ep_count=len(EPISODES), ep_minutes=5, revision=2,
        stage="scripted",
        arcs=[
            {
                "title": "The Break",
                "episodes": "1-2",
                "summary": "A breakup detonates when Daniel reveals messages from Maya's dead mother.",
            },
            {
                "title": "The Promise",
                "episodes": "3-6",
                "summary": "Each recovered object exposes how secrecy became control.",
            },
            {
                "title": "The Choice",
                "episodes": "7-8",
                "summary": "The final recording gives Maya agency and the couple an honest ending.",
            },
        ],
    )
    store.save_idea(SERIES_ID, (
        "A real-time relationship mystery about Maya and Daniel, a couple ending a "
        "seven-year relationship while packing their apartment. A hidden archive of "
        "messages from Maya's late mother turns one breakup into an eight-episode "
        "reckoning with grief, consent, protection, and the stories people tell to "
        "justify silence. There is no narrator; every revelation must live in performance."
    ))
    store.save_clarification(SERIES_ID, {
        "questions": [
            {"question": "What should drive the season?", "recommended": "Relationship mystery"},
            {"question": "Should the ending reconcile the couple?", "recommended": "Honest separation"},
            {"question": "How contained should the world feel?", "recommended": "One apartment, one weekend"},
            {"question": "Should the show use narration?", "recommended": "No narration"},
        ]
    })
    store.save_clarification_answers(SERIES_ID, [
        {"question": "Season engine", "answer": "Relationship mystery"},
        {"question": "Ending", "answer": "Honest separation"},
        {"question": "Setting", "answer": "One apartment, one weekend"},
        {"question": "Narration", "answer": "None"},
    ])
    store.save_confirmations(SERIES_ID, {
        "title": title,
        "genre": genre,
        "setting": setting,
        "include_narrator": False,
        "ep_count": len(EPISODES),
        "ep_minutes": 5,
        "genre_tags": ["Relationship Drama", "Mystery", "Romance", "Psychological"],
        "theme_tags": ["Being Heard", "Grief", "Consent", "Letting Go"],
    })

    store.save_blueprint(SERIES_ID, {
        "logline": (
            "As a couple packs the remains of their relationship, secret recordings "
            "from a dead mother force them to decide whether protection without consent "
            "is love, betrayal, or both."
        ),
        "story_world": (
            "The series unfolds over one rain-soaked weekend inside Maya and Daniel's "
            "small apartment. Boxes, shared objects, phone recordings, and the changing "
            "acoustics of an emptied home make the setting active and audio-readable."
        ),
        "main_storyline": (
            "Daniel is packing after seven years with Maya. In Episode 1, a blue mug "
            "from Maya's late mother turns quiet logistics into an emotional fight. "
            "Daniel's guarded phone suggests an affair; when Maya tries to finish one "
            "last plea, Daniel interrupts her with a single shouted ENOUGH. Her sentence "
            "is cut, every bed and effect disappears, and absolute silence follows. "
            "Daniel then reveals the messages came from Maya's dead mother, Elena. "
            "Across eight episodes, Maya, Daniel, and Maya's sister Priya reconstruct "
            "Elena's secret voice archive. Each recording is tied to an object they are "
            "packing and reveals a choice made without Maya's consent. The mystery is "
            "not whether Daniel loved Maya, but whether love can survive when one person "
            "decides what truth the other can bear. Maya ultimately chooses her residency "
            "and her own grief. Daniel accepts responsibility without demanding reunion. "
            "They separate honestly at sunrise, leaving the possibility of healing but "
            "not undoing the harm."
        ),
        "theme": "Love cannot substitute for consent; being protected is not the same as being heard.",
        "tone": "Raw, cinematic, restrained, psychologically intimate, ultimately bittersweet.",
        "story_beats": [
            "A packed blue mug exposes that Daniel's departure is final.",
            "A one-word shouted interruption ruptures the couple's ability to perform calm.",
            "Messages from Elena transform suspected infidelity into a grief mystery.",
            "Recovered recordings reveal that both partners built secret escape plans.",
            "Elena's final message rejects the protection pact she created.",
            "Maya and Daniel choose accountability and separation over a false romantic repair.",
        ],
        "characters": [
            {
                "name": "Maya", "role": "Lead", "gender": "Woman",
                "description": "A documentary sound editor whose need for truth is sharpened by unresolved grief.",
                "personality": "Perceptive, direct, loyal, impatient with ambiguity, emotionally brave.",
                "relationships": ["Daniel: partner of seven years", "Elena: late mother", "Priya: younger sister"],
                "backstory": "Maya missed her mother's lucid final hour and has never forgiven herself.",
                "physical_persona": "Stillness under pressure; she handles objects when words become dangerous.",
                "vocal_signature": "Warm low register, precise consonants, breath destabilizes before volume rises.",
                "vocal_direction": "Adult woman; grief held in the throat, then openly pleading without melodrama.",
                "voice_id": "Achernar", "is_narrator": False,
            },
            {
                "name": "Daniel", "role": "Lead", "gender": "Man",
                "description": "A conflict-avoidant architect who mistakes carrying secrets for protecting people.",
                "personality": "Controlled, observant, defensive, caring, capable of sudden intensity.",
                "relationships": ["Maya: partner of seven years", "Elena: secret confidante", "Priya: distrustful ally"],
                "backstory": "Daniel promised Elena he would release her recordings only when Maya was ready.",
                "physical_persona": "Keeps packing during conflict until his composure breaks.",
                "vocal_signature": "Low textured voice; clipped answers, one explosive shout, remorseful near-whisper afterward.",
                "vocal_direction": "Adult man; contained and dry until the single word ENOUGH escapes at full force.",
                "voice_id": "Algenib", "is_narrator": False,
            },
            {
                "name": "Elena", "role": "Catalyst / recorded voice", "gender": "Woman",
                "description": "Maya and Priya's late mother, present through scheduled recordings.",
                "personality": "Witty, loving, proud, controlling when afraid, capable of late self-reckoning.",
                "relationships": ["Maya: elder daughter", "Priya: younger daughter", "Daniel: keeper of the archive"],
                "backstory": "A degenerative diagnosis led Elena to create the secret archive before her death.",
                "physical_persona": "Heard through close, imperfect phone recordings rather than narration.",
                "vocal_signature": "Mature warmth with dry humor and occasional breathlessness.",
                "vocal_direction": "Mature woman; intimate phone-recording delivery, never ghostly or supernatural.",
                "voice_id": "Gacrux", "is_narrator": False,
            },
            {
                "name": "Priya", "role": "Supporting lead", "gender": "Woman",
                "description": "Maya's younger sister, practical enough to challenge every version of the truth.",
                "personality": "Fast, skeptical, affectionate, technically resourceful, unwilling to romanticize grief.",
                "relationships": ["Maya: older sister", "Elena: late mother", "Daniel: reluctant collaborator"],
                "backstory": "Priya managed Elena's cloud accounts but was excluded from the secret pact.",
                "physical_persona": "Moves quickly and fills space until a revelation makes her go still.",
                "vocal_signature": "Youthful clear pace; humor appears as pressure relief, not comic detour.",
                "vocal_direction": "Young adult woman; crisp, grounded, emotionally unsentimental.",
                "voice_id": "Leda", "is_narrator": False,
            },
        ],
    }, meta={
        "genre": genre,
        "setting": setting,
        "language": "English",
        "theme": "Being heard",
        "tone": "Raw and intimate",
    })
    store.save_story_analysis(SERIES_ID, {
        "strengths": [
            "A contained apartment and object-based revelations are highly legible in audio.",
            "The central mystery grows directly from character choices rather than plot machinery.",
            "The one-word interruption creates a memorable presentation moment with a measurable sonic payoff.",
        ],
        "weaknesses": [
            "A two-person opening risks visual sameness if performance and blocking are not varied.",
            "Elena's recordings could become exposition unless each changes a present relationship.",
        ],
        "opportunities": [
            "Each packed object can give an episode its own sonic motif and emotional question.",
            "Priya and Elena expand the vocal palette without weakening the intimate core.",
            "The mystery structure supports strong cliffhangers in five-minute episodes.",
        ],
        "threats": [
            "Too much score would cheapen the argument and reduce the impact of silence.",
            "A late romantic reconciliation would undercut the season's consent theme.",
        ],
        "genre_description": (
            "An intimate relationship drama structured like a mystery: romance supplies "
            "the emotional stakes, while recovered recordings provide thriller momentum."
        ),
        "genre_tags": ["Relationship Drama", "Mystery", "Romance", "Psychological"],
        "genre_distribution": {
            "action": 1, "drama": 45, "comedy": 2, "sci_fi": 0,
            "horror": 2, "thriller": 20, "romance": 30,
        },
        "theme_description": (
            "The series tests the difference between care and control, and asks whether "
            "truth delivered late can still restore agency."
        ),
        "themes": [
            {"label": "Being Heard", "percentage": 35},
            {"label": "Grief and Memory", "percentage": 25},
            {"label": "Consent versus Protection", "percentage": 25},
            {"label": "Letting Go", "percentage": 15},
        ],
    })
    store.save_voice_cast(SERIES_ID, {
        "Maya": "Achernar", "Daniel": "Algenib",
        "Elena": "Gacrux", "Priya": "Leda",
    })
    for outline in EPISODES:
        store.save_episode_outline(SERIES_ID, outline)
    store.save_episode_script(SERIES_ID, EPISODE_NUMBER, SCRIPT)
    store.save_episode_evaluation(SERIES_ID, EPISODE_NUMBER, {
        "points": [
            {
                "category": "Opening hook",
                "assessment": "The blue mug turns ordinary packing into immediate emotional evidence.",
                "suggestion": "Keep the first minute underplayed so the audience leans into the subtext.",
            },
            {
                "category": "Escalation",
                "assessment": "Phone suspicion steadily converts logistics into an interrogation.",
                "suggestion": "Allow only the planned crosstalk; clarity makes ENOUGH feel more violent.",
            },
            {
                "category": "Audio staging",
                "assessment": "The hard-cut sentence, dry shout, and absolute silence form the episode's signature beat.",
                "suggestion": "Never place a riser, impact, sob loop, or room tone inside the silence.",
            },
            {
                "category": "Cliffhanger",
                "assessment": "The dead-mother reveal converts a breakup story into the season mystery.",
                "suggestion": "End immediately after Maya states that her mother is dead.",
            },
        ],
        "stale": False,
    })

    existing_audio = store.load_episode(SERIES_ID, EPISODE_NUMBER)["audio"]
    if existing_audio and existing_audio.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        existing_audio["stale"] = True
        store.save_episode_audio(SERIES_ID, EPISODE_NUMBER, existing_audio)


def _usable_manifest(info: dict[str, Any]) -> bool:
    line_files = list(info.get("line_files") or [])
    durations = list(info.get("line_durations_ms") or [])
    return (
        info.get("script_fingerprint") == SCRIPT_FINGERPRINT
        and len(line_files) == len(SCRIPT)
        and len(durations) == len(SCRIPT)
        and all(Path(path).is_file() for path in line_files)
        and all(int(value) > 0 for value in durations)
    )


def _render_voices(force: bool) -> tuple[dict[str, Any], bool]:
    existing = store.load_episode(SERIES_ID, EPISODE_NUMBER)["audio"]
    if not force and _usable_manifest(existing):
        print("VOICE_STAGE=reused immutable line WAVs")
        return existing, False

    state = store.hydrate(SERIES_ID)

    def progress(done: int, total: int) -> None:
        print(f"VOICE_PROGRESS={done}/{total}", flush=True)

    manifest = audio_nodes.render_episode_audio(
        state, EPISODE_NUMBER, progress=progress,
    )
    manifest["script_fingerprint"] = SCRIPT_FINGERPRINT
    store.save_episode_audio(SERIES_ID, EPISODE_NUMBER, manifest)
    print("VOICE_STAGE=generated each dialogue line once")
    return manifest, True


def _editor_plan(source_durations: list[int]) -> list[dict[str, Any]]:
    edits: list[dict[str, Any]] = []
    slow_emotions = {"Sad", "Trembling", "Pleading", "Fear"}
    hot_emotions = {"Anger", "Determined", "Shouting"}
    pause_beats = {
        2: 650, 5: 500, 13: 650, 17: 750, 23: 650, 26: 700,
        35: 900, 37: 550, 48: 650, 51: 700, 55: 450,
        60: 600, 61: 800, 63: 650, 65: 1_100,
    }
    for index, line in enumerate(SCRIPT):
        emotion = line.get("emotion")
        rate = 0.96 if emotion in slow_emotions else 1.0
        gain = -0.6 if emotion in slow_emotions else 0.0
        if emotion in hot_emotions:
            rate, gain = 1.03, 0.8
        edits.append({
            "line": index,
            "pause_before_ms": 0,
            "pause_after_ms": pause_beats.get(index, 230),
            "rate": rate,
            "gain_db": gain,
        })

    edits[0].update({
        "pause_before_ms": 1_000, "pause_after_ms": 520,
        "rate": 0.93, "gain_db": -2.0, "fade_in_ms": 12,
    })
    # Controlled crosstalk as both characters stop listening.
    for line, overlap in ((40, 160), (43, 260), (44, 190), (53, 420),
                          (54, 330), (57, 180)):
        edits[line].update({
            "overlap_previous_ms": overlap,
            "pause_before_ms": 0,
            "pause_after_ms": 0,
        })

    # Maya's source take remains immutable; the editor removes its final phrase
    # and adds an anti-click fade. Daniel starts before that new clip end.
    cut_tail = max(800, min(1_500, round(source_durations[INTERRUPTED_LINE] * 0.09)))
    edits[INTERRUPTED_LINE].update({
        "pause_before_ms": 140,
        "pause_after_ms": 0,
        "rate": 0.93,
        "gain_db": 0.7,
        "trim_tail_ms": cut_tail,
        "fade_out_ms": 8,
    })
    edits[SHOUT_LINE].update({
        "overlap_previous_ms": 220,
        "interrupt": True,
        "pause_before_ms": 0,
        "pause_after_ms": 2_500,
        "rate": 1.04,
        "gain_db": 4.0,
        "fade_in_ms": 4,
    })
    edits[POST_SILENCE_LINE].update({
        "pause_before_ms": 0,
        "pause_after_ms": 700,
        "rate": 0.90,
        "gain_db": -4.0,
    })
    for index in range(61, len(edits)):
        edits[index]["rate"] = min(edits[index]["rate"], 0.94)
        edits[index]["gain_db"] = min(edits[index]["gain_db"], -1.8)
    return edits


def _assemble(items: list[dict[str, Any]], edits: list[dict[str, Any]]):
    return audio_engine.assemble_dialogue(items, edits, default_pause_ms=0)


def _fit_five_minutes(items: list[dict[str, Any]],
                      edits: list[dict[str, Any]]):
    dialogue, segments, offsets = _assemble(items, edits)
    # Spread missing time across genuine emotional beats, rather than appending
    # a fake block of silence at the end.
    anchors = [2, 5, 13, 17, 23, 26, 35, 37, 48, 51, 55, 60, 61, 63, 65]
    deficit = TARGET_DURATION_MS - len(dialogue)
    if deficit > 0:
        each = min(1_800, math.ceil(deficit / len(anchors)))
        for line in anchors:
            edits[line]["pause_after_ms"] += each
        dialogue, segments, offsets = _assemble(items, edits)
        remaining = TARGET_DURATION_MS - len(dialogue)
        if remaining > 0:
            # Spread larger remainders across ordinary conversational breaths;
            # reserve the last line only for an unavoidable rounding remainder.
            excluded = {40, 43, 44, 53, 54, 57, INTERRUPTED_LINE, SHOUT_LINE}
            secondary_anchors = [
                line_index
                for line_index in range(len(edits) - 1)
                if line_index not in excluded
            ]
            if secondary_anchors:
                each = math.ceil(remaining / len(secondary_anchors))
                for line_index in secondary_anchors:
                    if remaining <= 0:
                        break
                    increment = min(each, remaining)
                    edits[line_index]["pause_after_ms"] += increment
                    remaining -= increment
            if remaining > 0:
                edits[-1]["pause_after_ms"] += remaining
            dialogue, segments, offsets = _assemble(items, edits)
            final_remainder = TARGET_DURATION_MS - len(dialogue)
            if final_remainder > 0:
                edits[-1]["pause_after_ms"] += final_remainder
                dialogue, segments, offsets = _assemble(items, edits)
    elif deficit < 0:
        # First remove optional beat time, then make a bounded global pace
        # correction. TTS is never called again.
        excess = -deficit
        for line in anchors:
            removable = max(0, edits[line]["pause_after_ms"] - 180)
            take = min(removable, math.ceil(excess / max(1, len(anchors))))
            edits[line]["pause_after_ms"] -= take
            excess -= take
        dialogue, segments, offsets = _assemble(items, edits)
        if len(dialogue) > TARGET_DURATION_MS:
            ratio = min(1.10, len(dialogue) / TARGET_DURATION_MS)
            for edit in edits:
                if edit["line"] != SHOUT_LINE:
                    edit["rate"] = min(1.10, round(edit["rate"] * ratio, 4))
            dialogue, segments, offsets = _assemble(items, edits)
    return dialogue, segments, offsets


def _mix(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    items = [
        {
            "line_index": int(segment["line_index"]),
            "line_id": segment["line_id"],
            "speaker": segment["speaker"],
            "path": path,
        }
        for segment, path in zip(manifest["segments"], manifest["line_files"])
    ]
    edits = _editor_plan([int(value) for value in manifest["line_durations_ms"]])
    dialogue, segments, offsets = _fit_five_minutes(items, edits)
    dialogue = _conform(dialogue)
    duration_ms = len(dialogue)
    episode_dir = store.episode_dir(SERIES_ID, EPISODE_NUMBER)

    shout_start = int(segments[SHOUT_LINE]["start_ms"])
    score_start = max(0, int(segments[14]["start_ms"]) - 1_200)
    score_span = max(0, shout_start - score_start)
    score = audio_engine._loop_to(_conform(audio_engine.load(MUSIC_PATH)), score_span)
    if score_span:
        score = score + -12.0
        score = score.fade(
            from_gain=-9.0, to_gain=0.0, start=0,
            end=max(1, score_span - 300),
        ).fade_in(min(2_500, score_span)).fade_out(min(18, score_span))
        regions = audio_engine._dialogue_regions(
            segments, score_start, score_span, hold_ms=140,
        )
        score = audio_engine._apply_duck_envelope(
            score, regions, duck_db=-11.0,
            attack_ms=55, release_ms=260,
        )
    music_stem = _blank(duration_ms).overlay(score, position=score_start)

    # All non-voice sound stops when ENOUGH begins. Room tone returns only when
    # the first shaken post-silence line begins.
    room_source = audio_engine.load(ROOM_TONE_PATH)
    ambience_stem = _blank(duration_ms)
    ambience_stem = _overlay_span(
        ambience_stem, room_source, 0, shout_start,
        gain_db=10.0, fade_in_ms=500, fade_out_ms=12,
    )
    ambience_stem = _overlay_span(
        ambience_stem, room_source,
        int(segments[POST_SILENCE_LINE]["start_ms"]), duration_ms,
        gain_db=8.0, fade_in_ms=220, fade_out_ms=500,
    )

    sfx_stem = _blank(duration_ms)
    cup_at = max(0, int(segments[0]["start_ms"]) - 450)
    cup = _conform(audio_engine.load(CUP_PATH))[:700].fade_out(120) - 10.0
    sfx_stem = sfx_stem.overlay(cup, position=cup_at)
    sniff_at = max(int(segments[51]["end_ms"]) + 50,
                   int(segments[52]["start_ms"]) - 360)
    sniff_source = audio_engine.trim_edge_silence(audio_engine.load(SNIFF_PATH), {
        "silence_threshold_dbfs": -48, "max_trim_ms": 2_000,
        "keep_ms": 20, "chunk_ms": 5,
    })
    sniff = _conform(sniff_source)[:1_250].fade_in(15).fade_out(100) - 4.0
    sfx_stem = sfx_stem.overlay(sniff, position=sniff_at)

    dialogue_path = episode_dir / "ep01_dialogue_edit.wav"
    music_path = episode_dir / "ep01_music_stem.wav"
    ambience_path = episode_dir / "ep01_ambience_stem.wav"
    sfx_path = episode_dir / "ep01_sfx_stem.wav"
    final_path = episode_dir / "ep01_final.wav"
    audio_engine.export(dialogue, dialogue_path)
    audio_engine.export(music_stem, music_path)
    audio_engine.export(ambience_stem, ambience_path)
    audio_engine.export(sfx_stem, sfx_path)

    final = audio_engine.mix_and_master([
        {"audio": dialogue},
        {"audio": music_stem},
        {"audio": ambience_stem},
        {"audio": sfx_stem},
    ], {
        "duration_ms": duration_ms,
        "headroom_db": 3.0,
        "target_dbfs": -17.5,
        "peak_ceiling_dbfs": -1.0,
    })
    audio_engine.export(final, final_path)

    silence_start = int(segments[SHOUT_LINE]["end_ms"])
    silence_end = int(segments[POST_SILENCE_LINE]["start_ms"])
    silence_probe = final[min(silence_end, silence_start + 100):max(
        silence_start + 100, silence_end - 100,
    )]
    metrics = {
        "duration_ms": duration_ms,
        "target_duration_ms": TARGET_DURATION_MS,
        "source_dialogue_calls": len(SCRIPT),
        "maya_cut_at_ms": int(segments[INTERRUPTED_LINE]["end_ms"]),
        "shout_text": SCRIPT[SHOUT_LINE]["text"],
        "shout_start_ms": shout_start,
        "shout_overlap_ms": int(segments[SHOUT_LINE]["overlap_previous_ms"]),
        "all_beds_hard_stop_ms": shout_start,
        "absolute_silence_start_ms": silence_start,
        "absolute_silence_end_ms": silence_end,
        "absolute_silence_ms": max(0, silence_end - silence_start),
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
            "mood": "emotional",
            "start_ms": score_start,
            "end_ms": shout_start,
            "gain_db": -12.0,
            "duck_db": -11.0,
            "fade_in_ms": 2_500,
            "fade_out_ms": 18,
            "hard_stop_reason": "Daniel shouts ENOUGH mid-sentence",
        }],
        "sfx": [
            {"name": "tea_cup_clank", "at_ms": cup_at, "gain_db": -10.0},
            {"name": "post_crying_sniff", "at_ms": sniff_at, "gain_db": -4.0},
        ],
        "ambience": [
            {"name": "room_tone", "start_ms": 0,
             "end_ms": shout_start, "gain_db": 10.0},
            {"name": "room_tone",
             "start_ms": int(segments[POST_SILENCE_LINE]["start_ms"]),
             "end_ms": duration_ms, "gain_db": 8.0},
        ],
        "editor_notes": [
            "No narrator: the five-minute episode is carried by Maya and Daniel.",
            "Crosstalk increases only as both characters stop listening.",
            "Maya's line 59 is physically trimmed and anti-click faded; TTS is not rerun.",
            "Daniel's entire shouted line is the single word ENOUGH.",
            "Music and room tone stop at the shout; after it, 2.5 seconds are digitally silent.",
            "No sob loop, riser, boom, heartbeat, thunder, or door slam is used.",
        ],
        "metrics": metrics,
    }
    store.save_episode_sound_plan(SERIES_ID, EPISODE_NUMBER, plan)

    updated = dict(manifest)
    updated.update({
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "offsets": offsets,
        "segments": segments,
        "total_ms": duration_ms,
        "edited_line_durations_ms": [int(row["duration_ms"]) for row in segments],
        "dialogue_edit": str(dialogue_path),
        "music_stem": str(music_path),
        "ambience_stem": str(ambience_path),
        "sfx_stem": str(sfx_path),
        "final": str(final_path),
        "final_sha256": _sha256(final_path),
        "stale": False,
        "cinematic_editor": metrics,
    })
    store.save_episode_audio(SERIES_ID, EPISODE_NUMBER, updated)
    store.save_index(
        SERIES_ID, stage="episode_ready", ep_count=len(EPISODES), ep_minutes=5,
    )
    return updated, plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-voices", action="store_true",
        help="regenerate TTS instead of reusing immutable line WAVs",
    )
    args = parser.parse_args()
    required = (MUSIC_PATH, ROOM_TONE_PATH, SNIFF_PATH, CUP_PATH)
    missing = [path for path in required if path is None or not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing licensed assets: " + ", ".join(map(str, missing)))

    _write_project()
    artwork = image_service.ensure_series_images(SERIES_ID)
    manifest, generated = _render_voices(args.force_voices)
    updated, plan = _mix(manifest)
    result = {
        "series_id": SERIES_ID,
        "series_title": "The Things We Packed",
        "planned_episodes": len(EPISODES),
        "episode": EPISODE_NUMBER,
        "voices_generated_now": generated,
        "line_count": len(SCRIPT),
        "final": updated["final"],
        "sound_plan": str(
            store.episode_dir(SERIES_ID, EPISODE_NUMBER) / "sound_plan.json"
        ),
        "metrics": plan["metrics"],
        "artwork": artwork,
    }
    print("RESULT=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
