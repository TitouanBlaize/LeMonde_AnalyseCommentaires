"""Orchestration : RSS ou URL unique -> scraping -> résumé Mistral -> synthèse."""

import json
import logging
from datetime import datetime
from urllib.parse import urlparse

from . import analysis, config, feed
from .scraper import LeMondeSession

logger = logging.getLogger(__name__)


def _event(kind, **payload):
    payload["type"] = kind
    return payload


def _iso(value):
    """Normalise une date (datetime du flux RSS ou chaîne lue dans la page)."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def is_lemonde_url(url):
    host = urlparse(url or "").netloc.lower()
    return host == "lemonde.fr" or host.endswith(".lemonde.fr")


def _open_session(session):
    """Démarre le navigateur et tente la connexion, en annonçant chaque étape."""
    yield _event("status", step="browser", message="Ouverture du navigateur…")
    session.start()

    yield _event("status", step="login", message="Connexion au compte Le Monde…")
    if session.login():
        yield _event(
            "status",
            step="login_done",
            message="Connecté : les articles payants sont lus en entier.",
            logged_in=True,
        )
    else:
        yield _event(
            "status",
            step="login_failed",
            message=f"Connexion impossible ({session.login_error}). Les articles payants seront résumés sur leur seul extrait gratuit.",
            logged_in=False,
        )


def _process_article(session, article, with_comments=False, index=None, total=None):
    """Lit puis résume un article, en annonçant chaque étape.

    Le dernier événement produit est soit `article` (avec le résumé), soit `error`.
    `article` porte au minimum une `url` ; les autres champs (titre, rubrique, date)
    viennent du flux RSS quand ils existent, sinon de la page elle-même.
    """
    prefix = f"[{index}/{total}] " if index and total else ""
    label = (article.get("title") or article["url"])[:70]

    yield _event(
        "status",
        step="article",
        index=index,
        total=total,
        message=f"{prefix}Lecture : {label}…",
    )

    try:
        content = session.fetch_article(article["url"])
    except Exception as exc:
        logger.warning("Lecture impossible pour %s : %s", article["url"], exc)
        content = {"text": "", "chapo": "", "paywalled": False, "char_count": 0}

    merged = {**article, **{k: v for k, v in content.items() if v or k == "paywalled"}}
    merged["title"] = article.get("title") or content.get("title", "")
    label = merged["title"][:70] or label

    if not merged.get("text"):
        yield _event("error", message=f"Aucun texte lisible pour « {label} ».")
        return

    comments = []
    if with_comments:
        yield _event(
            "status",
            step="comments",
            index=index,
            total=total,
            message=f"{prefix}Lecture des contributions…",
        )
        try:
            comments = session.fetch_comments(article["url"])
        except Exception as exc:
            logger.warning("Contributions indisponibles pour %s : %s", article["url"], exc)

    yield _event(
        "status",
        step="analysis",
        index=index,
        total=total,
        message=f"{prefix}Analyse par Mistral…",
    )
    try:
        result = analysis.summarize_article(merged, comments)
    except Exception as exc:
        logger.exception("Analyse Mistral échouée pour %s", article["url"])
        yield _event("error", message=f"Analyse impossible pour « {label} » : {exc}")
        return

    yield _event(
        "article",
        index=index,
        total=total,
        data={
            "title": merged["title"],
            "url": merged["url"],
            "rubrique": merged.get("rubrique", ""),
            "author": merged.get("author", ""),
            "published": _iso(merged.get("published")),
            "paywalled": merged.get("paywalled", False),
            "nb_comments": len(comments),
            "analysis": result,
        },
    )


def generate_article_summary(url, with_comments=False, headless=None):
    """Résume un seul article, désigné par son URL (hors flux RSS).

    Même contrat d'événements que `generate_digest`, mais sans synthèse du jour :
    le `done` final porte `single: True`.
    """
    started_at = datetime.now()
    url = (url or "").strip()

    if not is_lemonde_url(url):
        yield _event(
            "error",
            message="Adresse invalide : attendu un lien d'article sur lemonde.fr.",
            fatal=True,
        )
        return

    session = LeMondeSession(headless=headless)
    summary = None
    try:
        yield from _open_session(session)

        article = {"url": url, "rubrique": feed.rubrique_from_url(url)}
        for event in _process_article(session, article, with_comments=with_comments):
            if event["type"] == "article":
                summary = event["data"]
            yield event
    finally:
        session.quit()

    if summary is None:
        yield _event("error", message="Cet article n'a pas pu être résumé.", fatal=True)
        return

    yield _event(
        "done",
        data={
            "single": True,
            "generated_at": started_at.isoformat(timespec="seconds"),
            "duration_s": round((datetime.now() - started_at).total_seconds()),
            "logged_in": session.logged_in,
            "login_error": session.login_error,
            "with_comments": with_comments,
            "articles": [summary],
        },
    )


def generate_digest(count=None, with_comments=False, headless=None):
    """Génère le digest article par article.

    Générateur d'événements (dictionnaires JSON-sérialisables) consommés par
    l'interface web : `status`, `article`, `done`, `error`. Un événement `error`
    portant `fatal` met fin au flux : le client doit fermer la connexion SSE,
    sinon le navigateur relancerait la génération de lui-même.
    """
    count = count or config.NB_ARTICLES
    started_at = datetime.now()
    summaries = []

    yield _event("status", step="feed", message="Récupération des derniers articles publiés…")
    try:
        articles = feed.fetch_latest_articles(limit=count)
    except Exception as exc:  # réseau, RSS indisponible…
        logger.exception("Échec de la récupération du flux RSS")
        yield _event("error", message=f"Impossible de lire le flux RSS du Monde : {exc}", fatal=True)
        return

    yield _event(
        "status",
        step="feed_done",
        message=f"{len(articles)} articles trouvés.",
        articles=[
            {"title": a["title"], "url": a["url"], "rubrique": a["rubrique"]} for a in articles
        ],
    )

    session = LeMondeSession(headless=headless)
    try:
        yield from _open_session(session)

        for index, article in enumerate(articles, start=1):
            for event in _process_article(
                session, article, with_comments=with_comments, index=index, total=len(articles)
            ):
                if event["type"] == "article":
                    summaries.append(event["data"])
                yield event
    finally:
        session.quit()

    if not summaries:
        yield _event("error", message="Aucun article n'a pu être analysé.", fatal=True)
        return

    yield _event("status", step="digest", message="Rédaction de la synthèse du jour…")
    try:
        overview = analysis.build_daily_digest(summaries)
    except Exception as exc:
        logger.exception("Synthèse globale échouée")
        overview = {"titre": "Revue de presse du jour", "synthese": f"(synthèse indisponible : {exc})", "tendances": [], "a_retenir": []}

    digest = {
        "generated_at": started_at.isoformat(timespec="seconds"),
        "duration_s": round((datetime.now() - started_at).total_seconds()),
        "logged_in": session.logged_in,
        "login_error": session.login_error,
        "with_comments": with_comments,
        "overview": overview,
        "articles": summaries,
    }
    save_digest(digest)
    yield _event("done", data=digest)


def save_digest(digest):
    """Archive le digest en JSON dans data/ et met à jour data/latest.json."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = digest["generated_at"].replace(":", "-")
    path = config.DATA_DIR / f"digest-{stamp}.json"
    payload = json.dumps(digest, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    (config.DATA_DIR / "latest.json").write_text(payload, encoding="utf-8")
    logger.info("Digest enregistré dans %s", path)
    return path


def load_latest_digest():
    path = config.DATA_DIR / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
