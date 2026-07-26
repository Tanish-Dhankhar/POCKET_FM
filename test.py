import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")  # Or replace with your API key
)

try:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input="Say 'API key is working!'"
    )

    print("✅ Success!")
    print(response.output_text)

except Exception as e:
    print("❌ Error:")
    print(e)