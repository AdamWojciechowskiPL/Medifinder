# START OF FILE: chrome_driver_factory.py (Wersja bez undetected-chromedriver, z trybem awaryjnym)

import logging
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

logger = logging.getLogger(__name__)

class ChromeDriverFactory:
    """
    Fabryka tworząca w pełni skonfigurowane instancje standardowego
    sterownika Selenium Chrome, z opcjami maskującymi i trybem awaryjnym.
    """

    def __init__(self, headless: bool = False, progress_callback=None):
        """
        Inicjalizuje fabrykę, akceptując i przechowując progress_callback.
        """
        self.headless = headless
        # Jeśli callback nie zostanie podany, użyj pustej funkcji lambda
        self.progress_callback = progress_callback or (lambda value, text: None)
        self._fallback_attempted = False

    def create_driver(self) -> webdriver.Chrome:
        """
        Główna metoda tworząca sterownik. W przypadku timeoutu (np. zablokowana sesja),
        wchodzi w tryb inteligentnego oczekiwania.
        """
        self.progress_callback(10, "Uruchamianie przeglądarki...")
        logger.info("Tworzenie standardowego sterownika Chrome WebDriver...")
        while True: # Nieskończona pętla, którą przerwiemy po sukcesie
            try:
                logger.info("Tworzenie standardowego sterownika Chrome WebDriver...")
                options = self._get_chrome_options()
                service = self._get_chrome_service()
                driver = webdriver.Chrome(service=service, options=options)
                self._apply_driver_settings(driver)
                logger.info("Sterownik Chrome WebDriver został pomyślnie utworzony i skonfigurowany.")
                return driver # Sukces! Zwróć sterownik i wyjdź z pętli.

            except WebDriverException as e:
                # Sprawdź, czy błąd to nasz znajomy "Read timed out"
                if 'Read timed out' in str(e):
                    logger.warning("Nie udało się utworzyć sterownika z powodu timeoutu. Prawdopodobnie sesja Windows jest zablokowana.")
                    logger.info("Aplikacja wstrzymuje próbę logowania i będzie próbować ponownie co 60 sekund...")
                    
                    # Czekaj 60 sekund przed następną próbą
                    time.sleep(60)
                    
                    # Kontynuuj pętlę, aby spróbować ponownie
                    continue
                else:
                    # Jeśli to inny błąd WebDrivera, spróbuj trybu awaryjnego
                    logger.error(f"Nie udało się utworzyć głównego sterownika Chrome: {e}", exc_info=True)
                    if not self._fallback_attempted:
                        self._fallback_attempted = True
                        logger.warning("Próba utworzenia sterownika w trybie awaryjnym (fallback)...")
                        # W trybie awaryjnym również używamy pętli
                        continue
                    raise WebDriverException(f"Wszystkie metody tworzenia sterownika zawiodły: {e}")
            
            except Exception as e:
                 # Obsługa innych, nieprzewidzianych błędów
                 logger.error(f"Wystąpił nieoczekiwany błąd podczas tworzenia sterownika: {e}", exc_info=True)
                 logger.info("Czekam 60 sekund przed ponowieniem próby...")
                 time.sleep(60)
                 continue

    def _get_chrome_options(self) -> webdriver.ChromeOptions:
        """Zwraca skonfigurowany obiekt ChromeOptions z opcjami maskującymi."""
        options = webdriver.ChromeOptions()
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        if self.headless:
            # Użyj nowego, lepszego trybu headless
            options.add_argument('--headless=new')
            options.add_argument(f'user-agent={user_agent}')
        
        # Opcje stabilności
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        
        # Opcje antydetekcyjne
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-notifications')
        options.add_argument("--lang=pl-PL")
        
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Preferencje przeglądarki
        prefs = {
            'profile.default_content_setting_values.notifications': 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option('prefs', prefs)
        return options

    def _get_chrome_service(self) -> Service:
        """Zwraca obiekt Service, zarządzając instalacją sterownika."""
        try:
            logger.info("Konfiguracja usługi ChromeDriver za pomocą WebDriverManager...")
            # Wyłączenie weryfikacji SSL, co pomaga w niektórych sieciach firmowych
            os.environ['WDM_SSL_VERIFY'] = '0'
            driver_path = ChromeDriverManager().install()
            return Service(driver_path)
        except Exception as e:
            logger.error(f"Nie udało się skonfigurować usługi ChromeDriver: {e}")
            raise

    def _apply_driver_settings(self, driver: webdriver.Chrome):
        """Aplikuje dodatkowe ustawienia do już utworzonej instancji sterownika."""
        driver.implicitly_wait(10)
        driver.set_page_load_timeout(45)
        
        if not self.headless:
            driver.maximize_window()
        
        # Dodatkowy skrypt maskujący, który usuwa flagę "webdriver" z przeglądarki
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def _create_fallback_driver(self) -> webdriver.Chrome:
        """Tworzy sterownik z minimalną konfiguracją w razie awarii głównej metody."""
        try:
            logger.info("Uruchamianie trybu awaryjnego z minimalną konfiguracją.")
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            
            service = self._get_chrome_service()
            driver = webdriver.Chrome(service=service, options=options)
            self._apply_driver_settings(driver)
            return driver
        except Exception as e:
            logger.critical(f"Tryb awaryjny tworzenia sterownika również zawiódł: {e}")
            raise WebDriverException("Nie udało się utworzyć sterownika Chrome nawet w trybie awaryjnym.")

# END OF FILE: chrome_driver_factory.py