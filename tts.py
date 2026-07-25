import os
import wave
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Set your API key through the environment or the project .env file.
load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.1-flash-tts-preview"

script = """
You are narrating an immersive cinematic audiobook.

Follow every emotion naturally. Pause where appropriate.
Change your voice according to each section.

[Calm]
It was an ordinary evening.
The rain tapped gently against the windows while the city slowly drifted to sleep.

[Curious]
Then...
A strange envelope appeared beneath the door.
There was no name.
No address.
Only a single symbol drawn in black ink.

[Whisper]
Don't open it...
Someone whispered from the darkness.

[Fear]
My heart began pounding.
Every instinct screamed that something was terribly wrong.
The room suddenly felt colder.

[Panic]
The lights went out!
I couldn't see anything.
Who's there?!
Answer me!

[Anger]
Show yourself!
I'm done hiding.
If you want me...
Come and face me!

[Relief]
A flashlight flickered on.
It was only my friend standing in the doorway,
breathing heavily and laughing.

[Joy]
We looked at each other...
Then burst into laughter.
I had never been happier to see another human being.

[Ending]
Little did we know...
The envelope had opened itself.
"""

response = client.models.generate_content(
    model=MODEL,
    contents=script,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Kore"  # Try: Kore, Aoede, Charon, Fenrir, Puck
                )
            )
        ),
    ),
)

audio = response.candidates[0].content.parts[0].inline_data.data

with wave.open("emotion_test.wav", "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(audio)

print("Saved emotion_test.wav")
