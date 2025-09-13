#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de scraping des commentaires d'articles du Monde
Auteur: Assistant Claude
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import csv
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import re

class LeMondeScraper:
    def __init__(self, headless=True, delay=2):
        """
        Initialise le scraper
        
        Args:
            headless (bool): Mode sans interface graphique
            delay (int): Délai entre les requêtes en secondes
        """
        self.delay = delay
        self.session = requests.Session()
        
        # Headers pour simuler un navigateur réel
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Configuration Selenium
        if headless:
            self.chrome_options = Options()
            self.chrome_options.add_argument('--headless')
            self.chrome_options.add_argument('--no-sandbox')
            self.chrome_options.add_argument('--disable-dev-shm-usage')
            self.chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            self.chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            self.chrome_options.add_experimental_option('useAutomationExtension', False)
    
    def scrape_with_requests(self, url):
        """
        Méthode de scraping avec requests (plus rapide mais limitée)
        
        Args:
            url (str): URL de l'article
            
        Returns:
            dict: Données extraites
        """
        try:
            print(f"Récupération de la page : {url}")
            response = self.session.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraction du titre de l'article
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "Titre non trouvé"
            
            # Recherche des commentaires dans différentes structures possibles
            comments = []
            
            # Structure 1: divs avec classes contenant "comment"
            comment_divs = soup.find_all('div', class_=re.compile(r'comment', re.I))
            for div in comment_divs:
                comment_text = div.get_text(strip=True)
                if len(comment_text) > 20:  # Filtre les commentaires trop courts
                    comments.append({
                        'text': comment_text,
                        'author': self._extract_author(div),
                        'date': self._extract_date(div)
                    })
            
            # Structure 2: Recherche dans les scripts JSON-LD ou autres
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and 'comments' in data:
                        for comment in data['comments']:
                            comments.append({
                                'text': comment.get('text', ''),
                                'author': comment.get('author', 'Anonyme'),
                                'date': comment.get('date', '')
                            })
                except json.JSONDecodeError:
                    continue
            
            return {
                'url': url,
                'title': title,
                'comments': comments,
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Erreur lors du scraping avec requests : {e}")
            return None
    
    def scrape_with_selenium(self, url, max_scroll=5):
        """
        Méthode de scraping avec Selenium (plus lente mais plus complète)
        
        Args:
            url (str): URL de l'article
            max_scroll (int): Nombre maximum de scrolls pour charger plus de commentaires
            
        Returns:
            dict: Données extraites
        """
        driver = None
        try:
            print(f"Ouverture de la page avec Selenium : {url}")
            driver = webdriver.Chrome(options=self.chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            driver.get(url)
            
            # Attendre que la page se charge
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Titre de l'article
            try:
                title = driver.find_element(By.TAG_NAME, "h1").text
            except:
                title = driver.title
            
            # Faire défiler pour charger plus de commentaires
            for i in range(max_scroll):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # Chercher et cliquer sur "Voir plus de commentaires" si disponible
                try:
                    load_more = driver.find_element(By.XPATH, "//*[contains(text(), 'commentaires') or contains(text(), 'Voir plus')]")
                    driver.execute_script("arguments[0].click();", load_more)
                    time.sleep(3)
                except:
                    pass
            
            # Extraction des commentaires
            comments = []
            
            # Sélecteurs possibles pour les commentaires
            comment_selectors = [
                "[class*='comment']",
                "[data-testid*='comment']",
                ".comment",
                ".discussion-item",
                "[role='article']"
            ]
            
            for selector in comment_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        if len(text) > 20:
                            comments.append({
                                'text': text,
                                'author': self._extract_author_selenium(elem),
                                'date': self._extract_date_selenium(elem)
                            })
                except:
                    continue
            
            return {
                'url': url,
                'title': title,
                'comments': comments,
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Erreur lors du scraping avec Selenium : {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def _extract_author(self, element):
        """Extrait le nom de l'auteur d'un commentaire (BeautifulSoup)"""
        author_selectors = ['span.author', '.username', '.user-name', '[class*="author"]']
        for selector in author_selectors:
            author_elem = element.select_one(selector)
            if author_elem:
                return author_elem.get_text(strip=True)
        return "Anonyme"
    
    def _extract_date(self, element):
        """Extrait la date d'un commentaire (BeautifulSoup)"""
        date_selectors = ['time', '.date', '.timestamp', '[datetime]']
        for selector in date_selectors:
            date_elem = element.select_one(selector)
            if date_elem:
                return date_elem.get('datetime') or date_elem.get_text(strip=True)
        return ""
    
    def _extract_author_selenium(self, element):
        """Extrait le nom de l'auteur d'un commentaire (Selenium)"""
        try:
            author = element.find_element(By.CSS_SELECTOR, "[class*='author'], .username, .user-name")
            return author.text.strip()
        except:
            return "Anonyme"
    
    def _extract_date_selenium(self, element):
        """Extrait la date d'un commentaire (Selenium)"""
        try:
            date_elem = element.find_element(By.CSS_SELECTOR, "time, .date, .timestamp, [datetime]")
            return date_elem.get_attribute('datetime') or date_elem.text.strip()
        except:
            return ""
    
    def save_to_json(self, data, filename):
        """Sauvegarde les données en JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Données sauvegardées dans {filename}")
    
    def save_to_csv(self, data, filename):
        """Sauvegarde les commentaires en CSV"""
        if not data or not data.get('comments'):
            print("Aucun commentaire à sauvegarder")
            return
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['URL', 'Titre', 'Auteur', 'Date', 'Commentaire'])
            
            for comment in data['comments']:
                writer.writerow([
                    data['url'],
                    data['title'],
                    comment['author'],
                    comment['date'],
                    comment['text']
                ])
        print(f"Commentaires sauvegardés dans {filename}")

def main():
    """Fonction principale"""
    url = "https://www.lemonde.fr/idees/article/2025/09/12/comment-la-politique-de-l-offre-detourne-l-argent-public-au-profit-des-plus-riches_6640595_3232.html"
    
    scraper = LeMondeScraper()
    
    print("=== Scraping des commentaires Le Monde ===\n")
    
    # Méthode 1: Avec requests (plus rapide)
    print("1. Tentative avec requests...")
    data = scraper.scrape_with_requests(url)
    
    if data and data['comments']:
        print(f"✓ {len(data['comments'])} commentaires trouvés avec requests")
    else:
        print("✗ Aucun commentaire trouvé avec requests")
        
        # Méthode 2: Avec Selenium (plus robuste)
        print("\n2. Tentative avec Selenium...")
        try:
            data = scraper.scrape_with_selenium(url)
            if data and data['comments']:
                print(f"✓ {len(data['comments'])} commentaires trouvés avec Selenium")
            else:
                print("✗ Aucun commentaire trouvé avec Selenium")
        except Exception as e:
            print(f"✗ Erreur avec Selenium: {e}")
            print("Note: Assurez-vous d'avoir ChromeDriver installé")
    
    # Sauvegarde des résultats
    if data:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scraper.save_to_json(data, f"lemonde_comments_{timestamp}.json")
        scraper.save_to_csv(data, f"lemonde_comments_{timestamp}.csv")
        
        print(f"\n=== Résumé ===")
        print(f"Titre: {data['title']}")
        print(f"URL: {data['url']}")
        print(f"Nombre de commentaires: {len(data['comments'])}")
        
        if data['comments']:
            print(f"\nPremier commentaire:")
            print(f"Auteur: {data['comments'][0]['author']}")
            print(f"Date: {data['comments'][0]['date']}")
            print(f"Texte: {data['comments'][0]['text'][:200]}...")
    else:
        print("\n⚠️ Aucune donnée récupérée. Le site pourrait bloquer le scraping.")
        print("Conseils:")
        print("- Utilisez un VPN")
        print("- Ajoutez des délais plus longs")
        print("- Vérifiez que l'article a des commentaires activés")

if __name__ == "__main__":
    main()