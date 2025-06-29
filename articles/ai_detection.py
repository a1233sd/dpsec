import os
import requests

SAPLING_API_KEY = os.getenv("SAPLING_API_KEY")  # или впиши ключ напрямую (не рекомендуется)

def detect_ai(text: str) -> float:
    url = "https://api.sapling.ai/api/v1/ai-detection"
    headers = {
        "Authorization": f"Bearer {SAPLING_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Предположим, что API возвращает вероятность в поле data['ai_probability']
        # Нужно уточнить в документации Sapling, как именно называется поле
        ai_prob = data.get("ai_probability", 0.0)  # пример
        return float(ai_prob) * 100  # в процентах
    except Exception as e:
        print("Ошибка при вызове Sapling AI detection:", e)
        return 0.0
