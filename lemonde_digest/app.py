"""Application Flask : interface locale du résumé quotidien Le Monde."""

import json
import logging

from flask import Flask, Response, jsonify, render_template, request

from . import config
from .digest import generate_article_summary, generate_digest, load_latest_digest

logger = logging.getLogger(__name__)


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def create_app():
    app = Flask(
        __name__,
        template_folder=str(config.BASE_DIR / "templates"),
        static_folder=str(config.BASE_DIR / "static"),
    )

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            nb_articles=config.NB_ARTICLES,
            model=config.MISTRAL_MODEL,
        )

    @app.get("/api/latest")
    def latest():
        """Dernier digest généré, pour réafficher sans tout relancer."""
        digest = load_latest_digest()
        if digest is None:
            return jsonify({"digest": None}), 404
        return jsonify({"digest": digest})

    @app.get("/api/digest/stream")
    def digest_stream():
        """Génère le digest et pousse la progression en Server-Sent Events."""
        count = request.args.get("count", type=int) or config.NB_ARTICLES
        count = max(1, min(count, 30))
        with_comments = request.args.get("comments") == "1"

        def stream():
            try:
                for event in generate_digest(count=count, with_comments=with_comments):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # garde-fou : l'UI doit toujours être prévenue
                logger.exception("Génération du digest interrompue")
                error = {"type": "error", "message": f"Erreur inattendue : {exc}", "fatal": True}
                yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

        return _sse(stream())

    @app.get("/api/article/stream")
    def article_stream():
        """Résume un article désigné par son URL, en Server-Sent Events."""
        url = request.args.get("url", "")
        with_comments = request.args.get("comments") == "1"

        def stream():
            try:
                for event in generate_article_summary(url, with_comments=with_comments):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("Résumé d'article interrompu")
                error = {"type": "error", "message": f"Erreur inattendue : {exc}", "fatal": True}
                yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

        return _sse(stream())

    return app


def _sse(generator):
    return Response(
        generator,
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
