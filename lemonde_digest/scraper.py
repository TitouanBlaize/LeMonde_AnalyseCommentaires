"""Session navigateur Le Monde : connexion, lecture des articles et des contributions."""

import logging
import re
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config

logger = logging.getLogger(__name__)

# Marqueurs de TRONCATURE, affichés à l'endroit où le texte s'interrompt.
# « Article réservé aux abonnés » n'en est pas un : ce libellé figure aussi dans
# l'en-tête des articles lus en entier par un compte abonné.
PAYWALL_MARKERS = (
    "Il vous reste",
    "La lecture de cet article est réservée",
)

# L'espace de discussion est rendu par le design system du Monde (« ds- »)
COMMENT_TEXT_SELECTOR = ".ds-comment__content"

# bloc affiché à la place de la liste quand personne n'a encore commenté
EMPTY_COMMENTS_SELECTOR = ".ds-comments-empty"

# le panneau charge la suite des contributions quand on défile SON conteneur
# (faire défiler la page, ou le dernier commentaire, ne déclenche rien)
SCROLL_COMMENTS_JS = """
let el = document.querySelector('.ds-comments-container');
while (el) {
  if (el.scrollHeight > el.clientHeight + 30) { el.scrollTop = el.scrollHeight; return true; }
  el = el.parentElement;
}
return false;
"""

COOKIE_XPATHS = (
    "//button[contains(., 'Continuer sans accepter')]",
    "//a[contains(., 'Continuer sans accepter')]",
    "//*[contains(text(), 'Continuer sans accepter')]",
)


class LoginError(RuntimeError):
    """La connexion au compte Le Monde a échoué."""


class LeMondeSession:
    """Pilote un navigateur pour lire les articles du Monde.

    S'utilise comme un gestionnaire de contexte :

        with LeMondeSession() as session:
            session.login()
            article = session.fetch_article(url)
    """

    def __init__(self, headless=None, browser=None):
        self.headless = config.HEADLESS if headless is None else headless
        self.browser = (browser or config.BROWSER).lower()
        self.driver = None
        self.logged_in = False
        self.login_error = None

    # ---------------------------------------------------------------- cycle de vie
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.quit()
        return False

    def start(self):
        if self.driver is not None:
            return
        if self.browser == "chrome":
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-blink-features=AutomationControlled")
            self.driver = webdriver.Chrome(options=options)
        else:
            options = webdriver.FirefoxOptions()
            if self.headless:
                options.add_argument("-headless")
            self.driver = webdriver.Firefox(options=options)
        self.driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
        logger.info("Navigateur %s démarré (headless=%s)", self.browser, self.headless)

    def quit(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None

    # ---------------------------------------------------------------- connexion
    def _dismiss_cookie_banner(self):
        """Refuse les cookies non essentiels si la bannière est affichée."""
        for xpath in COOKIE_XPATHS:
            try:
                element = self.driver.find_element(By.XPATH, xpath)
                self.driver.execute_script("arguments[0].click();", element)
                time.sleep(1)
                return True
            except WebDriverException:
                continue
        return False

    def login(self):
        """Tente la connexion avec les identifiants du .env.

        Retourne True si la session est authentifiée. En cas d'échec, `login_error`
        contient le message affiché par Le Monde et la lecture se poursuit en mode
        gratuit (articles payants tronqués à leur extrait public).
        """
        if self.logged_in:
            return True
        if not config.EMAIL_MONDE or not config.PASSWORD_MONDE:
            self.login_error = "EMAIL_MONDE / PASSWORD_MONDE absents du fichier .env"
            return False

        self.start()
        try:
            self.driver.get(config.LOGIN_URL)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            self._dismiss_cookie_banner()

            email_field = self.driver.find_element(By.ID, "email")
            email_field.clear()
            email_field.send_keys(config.EMAIL_MONDE)

            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(config.PASSWORD_MONDE)

            self.driver.find_element(By.ID, "submit-button").click()

            for _ in range(10):
                time.sleep(1.5)
                if "connexion" not in self.driver.current_url:
                    self.logged_in = True
                    logger.info("Connexion Le Monde réussie")
                    return True

            self.login_error = self._login_page_error() or "Connexion refusée par Le Monde"
        except (TimeoutException, WebDriverException) as exc:
            self.login_error = f"Erreur navigateur pendant la connexion : {exc.__class__.__name__}"

        logger.warning("Connexion Le Monde échouée : %s", self.login_error)
        return False

    def _login_page_error(self):
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        for element in soup.find_all(class_=re.compile("error|alert", re.I)):
            message = element.get_text(" ", strip=True)
            if message:
                return message
        return None

    # ---------------------------------------------------------------- lecture
    def _soup(self, url, wait_for=None):
        self.start()
        self.driver.get(url)
        if wait_for:
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_for))
                )
            except TimeoutException:
                pass
        else:
            time.sleep(1.5)
        return BeautifulSoup(self.driver.page_source, "html.parser")

    def fetch_comments(self, url, max_comments=None):
        """Renvoie les contributions publiées sous un article.

        L'espace de discussion n'est pas dans la page initiale : il faut cliquer sur
        « Commenter » pour que le panneau se charge, et il est réservé aux abonnés
        (sans connexion valide, la liste renvoyée est vide).
        """
        max_comments = max_comments or config.MAX_COMMENTS
        self.start()

        if self.driver.current_url.split("?")[0] != url.split("?")[0]:
            self.driver.get(url)
            time.sleep(1.5)

        opened = self.driver.execute_script(
            """
            const btn = [...document.querySelectorAll('button, a')]
              .find(el => /^commenter/i.test(el.innerText.trim()));
            if (!btn) return false;
            btn.scrollIntoView({block: 'center'});
            btn.click();
            return true;
            """
        )
        if not opened:
            logger.info("Pas d'espace de contributions pour %s", url)
            return []

        # on attend soit les contributions, soit le message « pas encore de réaction »,
        # pour ne pas patienter 20 s sur un article que personne n'a commenté
        def loaded(driver):
            if driver.find_elements(By.CSS_SELECTOR, COMMENT_TEXT_SELECTOR):
                return True
            return bool(driver.find_elements(By.CSS_SELECTOR, EMPTY_COMMENTS_SELECTOR))

        try:
            WebDriverWait(self.driver, 20).until(loaded)
        except TimeoutException:
            logger.info("Espace de contributions non chargé pour %s", url)
            return []

        if not self.driver.find_elements(By.CSS_SELECTOR, COMMENT_TEXT_SELECTOR):
            logger.info("Aucune contribution publiée pour %s", url)
            return []

        # le panneau charge les contributions au défilement : on insiste tant qu'il en arrive,
        # en tolérant deux passes sans nouveauté avant de conclure que tout est chargé
        previous, stagnant = 0, 0
        for _ in range(12):
            count = len(self.driver.find_elements(By.CSS_SELECTOR, COMMENT_TEXT_SELECTOR))
            if count >= max_comments:
                break
            stagnant = stagnant + 1 if count == previous else 0
            if stagnant >= 2:
                break
            previous = count
            self.driver.execute_script(SCROLL_COMMENTS_JS)
            time.sleep(2)

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        comments = []
        for node in soup.select(".ds-comment"):
            body = node.select_one(COMMENT_TEXT_SELECTOR)
            text = body.get_text(" ", strip=True) if body else ""
            if not text:
                continue
            author = node.select_one(".ds-comment-signature__name")
            date = node.select_one(".ds-comment-signature__date")
            comments.append(
                {
                    "author": author.get_text(" ", strip=True) if author else "Anonyme",
                    "date": date.get_text(" ", strip=True) if date else "",
                    "text": text,
                }
            )
            if len(comments) >= max_comments:
                break

        logger.info("%s contributions récupérées pour %s", len(comments), url)
        return comments

    def fetch_article(self, url):
        """Récupère le texte d'un article. Le texte est tronqué si l'article est payant."""
        soup = self._soup(url, wait_for="article")

        title_element = soup.find("h1")
        title = title_element.get_text(" ", strip=True) if title_element else ""

        chapo_element = soup.find(class_="article__desc") or soup.find(class_="article__kicker")
        chapo = chapo_element.get_text(" ", strip=True) if chapo_element else ""

        author_element = soup.find(class_="author__name") or soup.find(class_="article__author-link")
        author = author_element.get_text(" ", strip=True) if author_element else ""

        # date de publication : utile pour un article saisi à la main (hors flux RSS)
        published = None
        for attrs in ({"property": "og:article:published_time"}, {"property": "article:published_time"}):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                published = meta["content"]
                break

        paragraphs = []
        for selector in ("p.article__paragraph", ".article__content p", "article p"):
            found = soup.select(selector)
            if found:
                paragraphs = [p.get_text(" ", strip=True) for p in found]
                break
        text = "\n\n".join(p for p in paragraphs if len(p) > 40)

        page_text = soup.get_text(" ", strip=True)
        paywalled = any(marker in page_text for marker in PAYWALL_MARKERS) or bool(
            soup.select_one(".paywall, [class*='--paywall']")
        )

        return {
            "url": url,
            "title": title,
            "chapo": chapo,
            "author": author,
            "published": published,
            "text": text[: config.MAX_ARTICLE_CHARS],
            "paywalled": paywalled,
            "char_count": len(text),
        }
