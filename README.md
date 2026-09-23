# Résumé quotidien Le Monde

Application web locale qui résume les articles du Monde avec Mistral, de deux façons :

- **les 10 derniers articles publiés**, résumés un par un puis reliés par une synthèse du jour ;
- **un article précis**, dont on colle l'adresse dans la barre prévue à cet effet (utile pour un
  article plus ancien, absent du flux).

Dans les deux cas, une case à cocher ajoute — en option — une **synthèse des commentaires** des lecteurs.

## Lancer l'application

```bash
.venv/Scripts/python.exe run.py
```

Puis ouvrir http://127.0.0.1:5000 et cliquer sur **« Génère-moi un résumé des 10 derniers articles »**,
ou coller une URL d'article dans la barre **« Ou résumer un article précis »**.

Options : `--port 5001`, `--host 0.0.0.0`, `--debug`.

## Ce que fait le bouton rouge

1. **Flux RSS** — lecture de `https://www.lemonde.fr/rss/en_continu.xml`, tri par date de publication,
   les *N* articles les plus récents sont retenus (*N* réglable dans l'interface).
2. **Navigateur** — Firefox est piloté par Selenium, connexion au compte du `.env`
   (nécessaire pour lire les articles payants en entier).
3. **Lecture** — titre, chapô, auteur et corps de l'article ; puis, si la case
   « + commentaires » est cochée, les contributions des lecteurs.
4. **Résumé** — un appel Mistral par article : résumé, points clés, angle, et le cas échéant
   synthèse des commentaires (tonalité, thèmes, points de désaccord).
5. **Synthèse du jour** — un dernier appel relie les sujets entre eux (titre, fils rouges, à retenir).

La progression est diffusée en direct (Server-Sent Events) : chaque article s'affiche dès qu'il est résumé.
Chaque digest est archivé dans `data/digest-<horodatage>.json`, et le dernier est rejouable via
**« Voir le dernier résumé »** sans relancer le scraping.

## Résumer les commentaires (optionnel)

Décoché par défaut : un clic ne produit que le résumé de l'article. Coché, chaque article reçoit en plus
un encadré « Ce qu'en disent les lecteurs ».

L'espace de discussion n'est pas dans le HTML initial : il faut cliquer sur « Commenter » pour que le
panneau se charge, puis faire défiler pour obtenir les contributions suivantes (`.ds-comment` dans le
design system du Monde). Il est **réservé aux abonnés** : sans connexion valide, aucune contribution
n'est récupérée. Un article sans commentaire est détecté immédiatement (`.ds-comments-empty`) et
n'affiche pas d'encadré.

Compter environ deux fois plus de temps : ~74 s pour 3 articles commentés, contre ~30 s sans.
Volume réglable via `MAX_COMMENTS` (120 par défaut) et `MAX_COMMENT_CHARS` (15 000 caractères
envoyés au modèle).

## Résumer un article précis

La barre d'URL prend n'importe quel lien `lemonde.fr` — y compris un article ancien, hors du flux RSS —
et n'exécute que les étapes 2 à 4 : connexion, lecture, résumé (~15 s). Titre, rubrique, auteur et date
sont lus directement dans la page. Pas de synthèse du jour dans ce mode, et le résultat n'écrase pas
le dernier digest archivé. Une adresse hors `lemonde.fr` est refusée avec un message explicite.

## Configuration (`.env`)

Voir `.env.example`. Variables utilisées :

| Variable | Rôle |
| --- | --- |
| `EMAIL_MONDE`, `PASSWORD_MONDE` | compte abonné Le Monde |
| `MISTRAL_API_KEY` | clé API Mistral |
| `MISTRAL_MODEL` | modèle par défaut (`ministral-8b-latest`) |
| `MISTRAL_FALLBACK_MODELS` | modèles de repli en cas de 403/429 |
| `NB_ARTICLES`, `MAX_ARTICLE_CHARS` | volume par défaut du digest |
| `MAX_COMMENTS`, `MAX_COMMENT_CHARS` | volume de commentaires lus et envoyés au modèle |
| `SELENIUM_HEADLESS`, `SELENIUM_BROWSER` | `true`/`false`, `firefox` ou `chrome` |

### Sans connexion Le Monde

Si la connexion échoue, l'application **continue** : les articles payants sont alors résumés à partir
de leur seul extrait gratuit, et un bandeau le signale dans l'interface. Les commentaires, eux,
restent inaccessibles.

### Modèle Mistral

Les modèles `mistral-large-*` renvoient `403 tier_not_allowed` avec une clé gratuite, et
`mistral-small/medium` répondent `429` une fois le quota épuisé. Le défaut `ministral-8b-latest`
fonctionne en offre gratuite ; en cas d'abonnement payant, préférer
`MISTRAL_MODEL="mistral-large-latest"` dans le `.env`.

## Structure

```
run.py                     point d'entrée (serveur Flask)
lemonde_digest/
  config.py                variables d'environnement et réglages
  feed.py                  derniers articles publiés (RSS)
  scraper.py               session Selenium : login, articles et contributions
  analysis.py              appels Mistral (résumé par article, synthèse du jour)
  digest.py                orchestration (digest ou article seul) + archivage JSON
  app.py                   routes Flask et flux SSE
templates/index.html       interface
static/                    style.css, app.js
data/                      digests archivés (ignoré par git)
Exemple analyse article.ipynb   notebook d'origine (analyse d'un article unique)
```

## Prérequis

- Python 3.11+ et les dépendances : `pip install -r requirements.txt`
- Firefox installé (le pilote geckodriver est téléchargé automatiquement par Selenium)
