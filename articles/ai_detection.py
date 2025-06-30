# articles/ai_detection.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SAPLING_API_KEY = os.getenv("SAPLING_API_KEY")

def detect_ai(text: str) -> float:
    """
    Возвращает вероятность AI-генерации текста от Sapling API.
    """
    url = "https://api.sapling.ai/api/v1/aidetect"
    headers = {
        "Authorization": f"Bearer {SAPLING_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "key": SAPLING_API_KEY,
        "text": text
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        result = response.json()
        prob = result.get("ai_probability", 0.0)
        return round(float(prob) * 100, 2)
    else:
        print("Sapling API error:", response.status_code, response.text)
        return 0.0
