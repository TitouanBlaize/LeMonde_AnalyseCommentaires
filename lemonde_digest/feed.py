"""Récupération des derniers articles publiés sur lemonde.fr via le flux RSS."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from . import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _parse_date(item):
    raw = item.findtext("pubDate")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def rubrique_from_url(url):
    """Déduit la rubrique depuis l'URL (https://www.lemonde.fr/<rubrique>/article/...)."""
    parts = [p for p in url.split("/") if p]
    if len(parts) >= 3:
        return parts[2].replace("-", " ").capitalize()
    return "Le Monde"


def fetch_latest_articles(limit=None, feed_url=None):
    """Retourne les `limit` derniers articles publiés, du plus récent au plus ancien."""
    limit = limit or config.NB_ARTICLES
    feed_url = feed_url or config.FEED_URL

    response = requests.get(feed_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    articles = []
    seen = set()
    for item in root.findall("./channel/item"):
        url = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not url or "/article/" not in url or url in seen:
            continue
        seen.add(url)
        articles.append(
            {
                "url": url,
                "title": title,
                "description": (item.findtext("description") or "").strip(),
                "published": _parse_date(item),
                "rubrique": rubrique_from_url(url),
            }
        )

    oldest = datetime.min.replace(tzinfo=timezone.utc)
    articles.sort(key=lambda a: a["published"] or oldest, reverse=True)
    logger.info("Flux RSS : %s articles trouvés, %s retenus", len(articles), min(limit, len(articles)))
    return articles[:limit]
