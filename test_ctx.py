import asyncio
from openai import AsyncOpenAI
import os

async def main():
    client = AsyncOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )
    
    # Send a very long prompt to see if it truncates
    long_prompt = "A" * 10000
    
    try:
        response = await client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": long_prompt + "\n\nRepeat my last word."}],
            extra_body={"options": {"num_ctx": 16384}}
        )
        print("Success:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
