#articles/external_search.py
import os
import requests
from dotenv import load_dotenv
from .cache_utils import get_cached_result, set_cached_result

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")


def search_google_fragment(query):
    """
    Выполняет Google Custom Search и возвращает найденные результаты.
    Использует кэширование для снижения количества запросов.
    """
    cached = get_cached_result(query)
    if cached is not None:
        print("[Google Search] Используется кэш для запроса.")
        return cached

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        print("[Google Search] Ошибка: GOOGLE_API_KEY или GOOGLE_CSE_ID не заданы.")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": 5,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as e:
        if response.status_code == 429:
            print("[Google Search] Превышен лимит запросов (429). Пропускаем поиск.")
        else:
            print(f"[Google Search Error] HTTP Error: {e}")
        return []
    except requests.RequestException as e:
        print(f"[Google Search Error] Request Exception: {e}")
        return []

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("link"),
            "snippet": item.get("snippet"),
        })
    print(f"[Google Search] Найдено совпадений: {len(results)}")

    # Сохраняем в кэш
    set_cached_result(query, results)

    return results
