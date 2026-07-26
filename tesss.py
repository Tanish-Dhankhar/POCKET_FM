from openai import OpenAI

# Paste your API key here
API_KEY = "your-api-key-here"

client = OpenAI(api_key=API_KEY)

try:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input="Hello! If this works, reply with: API key is working."
    )

    print("✅ API key is working!")
    print(response.output_text)

except Exception as e:
    print("❌ Error:")
    print(e)