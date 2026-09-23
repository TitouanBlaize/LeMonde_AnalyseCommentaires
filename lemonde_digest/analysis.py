"""Résumé des articles — et de leurs contributions — avec l'API Mistral."""

import json
import logging
import time

from mistralai import Mistral
from mistralai.models import SDKError

from . import config

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        if not config.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY absent du fichier .env")
        _client = Mistral(api_key=config.MISTRAL_API_KEY)
    return _client


def _complete(prompt):
    """Appelle Mistral en JSON, avec réessai sur quota et repli sur un autre modèle.

    Une clé gratuite est limitée en débit et n'a pas accès à tous les modèles :
    on réessaie quelques fois, puis on bascule sur les modèles de secours.
    """
    models = [config.MISTRAL_MODEL] + [
        m for m in config.MISTRAL_FALLBACK_MODELS if m != config.MISTRAL_MODEL
    ]
    last_error = None

    for model in models:
        for attempt, pause in enumerate((2, 5, 10)):
            try:
                response = get_client().chat.complete(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                if model != config.MISTRAL_MODEL:
                    logger.info("Modèle de secours utilisé : %s", model)
                return response.choices[0].message.content
            except SDKError as exc:
                last_error = exc
                if exc.status_code == 429 and attempt < 2:
                    logger.warning("Quota Mistral atteint (%s), nouvelle tentative dans %ss", model, pause)
                    time.sleep(pause)
                    continue
                logger.warning("Modèle %s indisponible (HTTP %s)", model, exc.status_code)
                break

    raise RuntimeError(f"Aucun modèle Mistral disponible ({last_error})")


def _complete_json(prompt):
    """Appelle Mistral en exigeant une réponse JSON et la décode."""
    content = _complete(prompt)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Réponse Mistral non JSON, renvoyée en texte brut")
        return {"resume": content}


def summarize_article(article, comments=None):
    """Résume un article et, si des contributions sont fournies, ce qu'en disent les lecteurs.

    `article` est le dictionnaire renvoyé par `LeMondeSession.fetch_article`,
    enrichi des métadonnées RSS (titre, rubrique, description). `comments` est la
    liste renvoyée par `LeMondeSession.fetch_comments`.
    """
    body = article.get("text") or article.get("description") or ""
    if not body.strip():
        body = article.get("title", "")

    sections = [
        "Tu es un journaliste chargé de préparer une revue de presse quotidienne.",
        "Résume l'article du Monde ci-dessous de façon factuelle, sans invention.",
        "",
        f"TITRE : {article.get('title', '')}",
        f"RUBRIQUE : {article.get('rubrique', '')}",
        f"CHAPO : {article.get('chapo') or article.get('description', '')}",
        "",
        "TEXTE DE L'ARTICLE :",
        body[: config.MAX_ARTICLE_CHARS],
    ]

    if article.get("paywalled"):
        sections.append(
            "\nATTENTION : seul le début de l'article est accessible (article payant). "
            "Résume ce qui est disponible, sans extrapoler la suite."
        )

    if comments:
        lignes = "\n".join(f"- {c['author']} : {c['text']}" for c in comments)
        sections += [
            "",
            f"CONTRIBUTIONS DES LECTEURS ({len(comments)} au total, une par ligne) :",
            lignes[: config.MAX_COMMENT_CHARS],
        ]
        schema_commentaires = (
            '  "commentaires": {'
            '"synthese": "3 à 4 phrases sur ce que disent les lecteurs", '
            '"tonalite": "une phrase sur la tonalité dominante", '
            '"themes": [{"theme": "nom du thème", "occurrences": nombre de contributions concernées}], '
            '"clivages": ["1 à 3 points de désaccord entre lecteurs"]}'
        )
    else:
        schema_commentaires = '  "commentaires": null'

    sections += [
        "",
        "Réponds uniquement en JSON avec exactement ces clés :",
        "{",
        '  "resume": "4 à 6 phrases résumant l\'article",',
        '  "points_cles": ["3 à 5 puces courtes"],',
        '  "angle": "une phrase sur l\'angle ou l\'enjeu principal",',
        schema_commentaires,
        "}",
    ]

    result = _complete_json("\n".join(sections))
    result.setdefault("resume", "")
    result.setdefault("points_cles", [])
    result.setdefault("angle", "")
    result.setdefault("commentaires", None)
    return result


def build_daily_digest(summaries):
    """Produit la synthèse globale à partir des résumés déjà calculés."""
    lines = []
    for index, item in enumerate(summaries, start=1):
        lines.append(f"{index}. [{item.get('rubrique', '')}] {item.get('title', '')}")
        lines.append(f"   {item.get('analysis', {}).get('resume', '')}")

    prompt = "\n".join(
        [
            "Tu es rédacteur en chef et tu ouvres la revue de presse du jour.",
            "Voici les résumés des derniers articles publiés par Le Monde :",
            "",
            "\n".join(lines),
            "",
            "Réponds uniquement en JSON avec exactement ces clés :",
            "{",
            '  "titre": "un titre court pour la journée",',
            '  "synthese": "un paragraphe de 5 à 8 phrases reliant les sujets du jour",',
            '  "tendances": ["3 à 5 tendances ou fils rouges, une phrase chacun"],',
            '  "a_retenir": ["les 3 sujets les plus importants, une phrase chacun"]',
            "}",
        ]
    )

    result = _complete_json(prompt)
    result.setdefault("titre", "Revue de presse du jour")
    result.setdefault("synthese", "")
    result.setdefault("tendances", [])
    result.setdefault("a_retenir", [])
    return result
