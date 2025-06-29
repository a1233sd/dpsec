import os
import django
import requests
from dotenv import load_dotenv
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')  # <- замени на свой проект
django.setup()

from articles.models import Report

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

def search_google_fragment(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": 5
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("link"),
            "snippet": item.get("snippet")
        })
    return results

if __name__ == "__main__":
    report = Report.objects.get(id=5)
    content = report.content

    sentences = re.split(r'(?<=[.!?])\s+', content)
    fragments = sentences[:3]

    for i, frag in enumerate(fragments, 1):
        print(f"\nФрагмент {i}: {frag}\nРезультаты поиска:")
        try:
            search_results = search_google_fragment(frag)
            for res in search_results:
                print(f"- {res['title']} ({res['url']})")
        except requests.HTTPError as e:
            print(f"Ошибка при поиске: {e}")
