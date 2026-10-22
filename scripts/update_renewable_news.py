from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import json
import re
import sys
from urllib.error import URLError
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "noticias.json"
FEEDS = (
    ("El Periódico de la Energía", "https://elperiodicodelaenergia.com/feed/", False),
    ("pv magazine España", "https://www.pv-magazine.es/feed/", False),
)
RENEWABLE_TERMS = (
    "renovable",
    "fotovoltaica",
    "solar",
    "eolica",
    "eolico",
    "energia limpia",
    "energias limpias",
    "autoconsumo",
    "hidrogeno verde",
    "biomasa",
    "geotermia",
)


def text_for(element: ET.Element, name: str) -> str:
    value = element.findtext(name) or ""
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )


def parse_feed(name: str, url: str, renewable_only: bool) -> list[dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "GEENIUS Energy News/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    articles = []
    for item in root.findall("./channel/item"):
        title = text_for(item, "title")
        link = text_for(item, "link")
        published = text_for(item, "pubDate")
        description = text_for(item, "description")
        if not title or not link or not published:
            continue

        if renewable_only:
            searchable = normalized(f"{title} {description}")
            if not any(term in searchable for term in RENEWABLE_TERMS):
                continue

        publication_date = parsedate_to_datetime(published)
        if publication_date.tzinfo is None:
            publication_date = publication_date.replace(tzinfo=timezone.utc)
        articles.append(
            {
                "titulo": title,
                "url": link,
                "fuente": name,
                "fecha": publication_date.astimezone(timezone.utc).isoformat(),
            }
        )
    return articles


def main() -> None:
    articles = []
    for name, url, renewable_only in FEEDS:
        try:
            articles.extend(parse_feed(name, url, renewable_only))
        except (URLError, OSError, ET.ParseError) as error:
            print(f"No se pudo leer el RSS de {name}: {error}", file=sys.stderr)

    feed_priority = {name: index for index, (name, _, _) in enumerate(FEEDS)}
    articles.sort(
        key=lambda article: (
            -feed_priority[article["fuente"]],
            article["fecha"],
        ),
        reverse=True,
    )
    unique_articles = []
    seen_urls = set()
    for article in articles:
        if article["url"] not in seen_urls:
            unique_articles.append(article)
            seen_urls.add(article["url"])
        if len(unique_articles) == 3:
            break

    if not unique_articles:
        raise RuntimeError("No se encontraron noticias del sector energético en los RSS.")

    data = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "noticias": unique_articles,
    }
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Se actualizaron {len(unique_articles)} noticias en {OUTPUT.name}.")


if __name__ == "__main__":
    main()
