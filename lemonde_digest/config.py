"""Configuration centrale de l'application (variables d'environnement et constantes)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _as_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "oui", "on")


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Identifiants Le Monde (abonnement) : sans eux, les articles payants sont tronqués
EMAIL_MONDE = os.getenv("EMAIL_MONDE")
PASSWORD_MONDE = os.getenv("PASSWORD_MONDE")

# Mistral
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
# ministral-8b-latest est accessible avec une clé gratuite ; les modèles "large"
# renvoient 403/429 hors abonnement payant, d'où la chaîne de repli.
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "ministral-8b-latest")
MISTRAL_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("MISTRAL_FALLBACK_MODELS", "mistral-small-latest,open-mistral-nemo").split(",")
    if m.strip()
]

# Flux RSS "en continu" : les derniers articles publiés, toutes rubriques confondues
FEED_URL = os.getenv("LEMONDE_FEED_URL", "https://www.lemonde.fr/rss/en_continu.xml")
LOGIN_URL = "https://secure.lemonde.fr/sfuser/connexion"

# Réglages du digest
NB_ARTICLES = _as_int(os.getenv("NB_ARTICLES"), 10)
MAX_ARTICLE_CHARS = _as_int(os.getenv("MAX_ARTICLE_CHARS"), 12000)
MAX_COMMENTS = _as_int(os.getenv("MAX_COMMENTS"), 120)
MAX_COMMENT_CHARS = _as_int(os.getenv("MAX_COMMENT_CHARS"), 15000)

# Selenium
HEADLESS = _as_bool(os.getenv("SELENIUM_HEADLESS"), True)
BROWSER = os.getenv("SELENIUM_BROWSER", "firefox").lower()
PAGE_LOAD_TIMEOUT = _as_int(os.getenv("PAGE_LOAD_TIMEOUT"), 30)

# Sorties
DATA_DIR = BASE_DIR / "data"
LOG_FILE = BASE_DIR / "app.log"
