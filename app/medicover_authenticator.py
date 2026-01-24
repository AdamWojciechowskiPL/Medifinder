import json
import time
import logging
from typing import Optional, Dict
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from .chrome_driver_factory import ChromeDriverFactory
from .login_form_handler import LoginFormHandler

logger = logging.getLogger(__name__)

class MedicoverAuthenticator:
    LOGIN_URL = "https://login-online24.medicover.pl/" # ZMIANA: Użyjemy krótszego, głównego URL
    SUCCESS_URL_SUBSTRING = "online24.medicover.pl/home"
    
    def __init__(self, headless: bool = False, progress_callback=None):
        """Inicjalizuje authenticator."""
        self.headless = headless
        self.progress_callback = progress_callback or (lambda value, text: None)
        
        # Kluczowy element: Przekaż callback dalej w dół do fabryki
        self.driver_factory = ChromeDriverFactory(
            headless=self.headless,
            progress_callback=self.progress_callback
        )
        self.auth_info: Dict = {'login_attempts': 0}

    def login(self, username: str, password: str) -> Optional[str]:
        self.auth_info['login_attempts'] += 1
        logger.info(f"Rozpoczynanie próby logowania #{self.auth_info['login_attempts']}...")
        
        driver = None
        try:
            driver = self.driver_factory.create_driver()
            
            self.progress_callback(25, "Otwieranie strony logowania...")
            logger.info(f"Nawigacja do strony logowania: {self.LOGIN_URL}")
            driver.get(self.LOGIN_URL)
            
            self.progress_callback(40, "Wprowadzanie danych...")
            form_handler = LoginFormHandler(driver)
            if not form_handler.fill_and_submit_login_form(username, password):
                logger.error("Nie udało się wypełnić i wysłać formularza logowania.")
                return None
            self.progress_callback(60, "Logowanie, proszę czekać...")
            if not self._wait_for_successful_redirect(driver):
                logger.error("Przekierowanie po zalogowaniu nie powiodło się lub upłynął czas oczekiwania.")
                return None


            self.progress_callback(80, "Pobieranie danych sesji...")
            token = self._extract_bearer_token(driver)

            self.progress_callback(95, "Finalizowanie...")
            if token:
                logger.info("Pomyślnie wyodrębniono token Bearer.")
                self.auth_info['last_successful_login'] = datetime.now().isoformat()
            else:
                logger.error("Nie udało się wyodrębnić tokenu Bearer po zalogowaniu.")

            return token

        except WebDriverException as e:
            logger.error(f"Wystąpił krytyczny błąd WebDrivera: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Wystąpił nieoczekiwany błąd podczas procesu logowania: {e}", exc_info=True)
            return None
        finally:
            if driver:
                driver.quit()
                logger.info("Przeglądarka została zamknięta.")

    def _wait_for_successful_redirect(self, driver: webdriver.Chrome, timeout: int = 30) -> bool:
        logger.info(f"Oczekiwanie na przekierowanie do strony głównej (max {timeout}s)...")
        try:
            WebDriverWait(driver, timeout).until(EC.url_contains(self.SUCCESS_URL_SUBSTRING))
            logger.info(f"Przekierowanie udane. Aktualny URL: {driver.current_url}")
            return True
        except TimeoutException:
            logger.error(f"Nie udało się doczekać na URL zawierający '{self.SUCCESS_URL_SUBSTRING}'.")
            logger.error(f"Ostateczny URL: {driver.current_url}")
            return False

    def _extract_bearer_token(self, driver: webdriver.Chrome) -> Optional[str]:
        logger.info("Próba wyodrębnienia tokenu z localStorage...")
        oidc_storage_key = "oidc.user:https://login-online24.medicover.pl/:web"
        
        # ZMIANA: Skrócono czas oczekiwania z 5 do 2 sekund.
        time.sleep(2) 
        
        try:
            oidc_data_raw = driver.execute_script(f"return localStorage.getItem('{oidc_storage_key}');")
            if not oidc_data_raw:
                logger.warning(f"Nie znaleziono danych w localStorage pod kluczem: {oidc_storage_key}")
                return None

            oidc_data = json.loads(oidc_data_raw)
            access_token = oidc_data.get('access_token')

            if access_token and isinstance(access_token, str) and len(access_token) > 50:
                logger.info(f"Znaleziono 'access_token' o długości {len(access_token)}.")
                return access_token
            
            id_token = oidc_data.get('id_token')
            if id_token and isinstance(id_token, str) and len(id_token) > 50:
                logger.warning("Nie znaleziono 'access_token', używanie 'id_token' jako fallback.")
                return id_token

            logger.error("Znaleziono obiekt OIDC, ale nie zawiera on prawidłowego 'access_token' ani 'id_token'.")
            return None

        except Exception as e:
            logger.error(f"Wystąpił błąd podczas ekstrakcji tokenu: {e}", exc_info=True)
            return None

    def close(self):
        logger.info("Authenticator nie zarządza trwałymi zasobami do zamknięcia.")

    def get_auth_info(self) -> Dict:
        self.auth_info['headless_mode'] = self.headless
        return self.auth_info