#!/usr/bin/env python3
"""Point d'entrée : lance l'interface web locale du résumé quotidien Le Monde."""

import argparse

from lemonde_digest.app import configure_logging, create_app


def main():
    parser = argparse.ArgumentParser(description="Résumé quotidien Le Monde")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    configure_logging()
    app = create_app()
    print(f"\n  Interface disponible sur http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
