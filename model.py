import google.generativeai as genai
from dotenv import load_dotenv
import os
import requests
import time
import random

# Load environment variables from .env file
load_dotenv()
api_key = os.getenv("gemini_token")

# Configure Gemini
genai.configure(api_key=api_key)

def get_ai_content(
    prompt,
    max_retries=3,
    base_delay=2,
    temperature=0.0,
    top_p=0.95,
    top_k=40,
    
):
    retry_count = 0

    while retry_count <= max_retries:
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                contents=prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature
                )
            )

            content_text = response.candidates[0].content.parts[0].text

            return content_text

        except Exception as e:
            error_message = str(e)
            

            if "503" in error_message or "UNAVAILABLE" in error_message.upper():
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                print(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                break

    
    return None