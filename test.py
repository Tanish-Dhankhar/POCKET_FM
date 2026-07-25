import os
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.1-flash-lite"   # Change this

response = client.models.generate_content(
    model=MODEL,
    contents="Write a short story about a detective cat in exactly 50 words."
)

print(response.text)