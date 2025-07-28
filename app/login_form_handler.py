# --- START OF FILE login_form_handler.py (Bez sprawdzania cookie) ---

import logging
import time
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)

class LoginFormHandler:
    """
    Zarządza procesem wypełniania i wysyłania formularza logowania.
    Wersja zoptymalizowana, bez sprawdzania baneru cookie.
    """

    def __init__(self, driver: WebDriver, timeout: int = 10):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def fill_and_submit_login_form(self, username: str, password: str) -> bool:
        """
        Główna metoda orkiestrująca wypełnienie i wysłanie formularza.
        """
        try:
            # KROK USUNIĘTY: Sprawdzanie baneru cookie.

            # Od razu przechodzimy do wyszukiwania pól formularza.
            username_field = self._find_element(["input[name='Input.Username']"], "pole użytkownika")
            if not username_field: return False
            self._fill_field(username_field, username, "użytkownik")

            password_field = self._find_element(["input[name='Input.Password']"], "pole hasła")
            if not password_field: return False
            self._fill_field(password_field, password, "hasło")

            self._handle_terms_checkbox()

            submit_button = self._find_element(["button[name='Input.Button']"], "przycisk Zaloguj")
            if not submit_button: return False
            
            logger.info("Wysyłanie formularza logowania...")
            self.driver.execute_script("arguments[0].click();", submit_button)
            
            return True
        except Exception as e:
            logger.error(f"Wystąpił błąd podczas obsługi formularza: {e}", exc_info=True)
            return False

    def _find_element(self, selectors: list[str], element_name: str) -> WebElement | None:
        """Próbuje znaleźć element używając listy selektorów CSS."""
        logger.debug(f"Wyszukiwanie elementu: {element_name}...")
        for selector in selectors:
            try:
                element = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                logger.info(f"Znaleziono {element_name} za pomocą selektora: '{selector}'")
                return element
            except TimeoutException:
                logger.debug(f"Selektor '{selector}' nie znalazł elementu w zadanym czasie.")
                continue
        logger.error(f"Nie udało się znaleźć elementu: {element_name} za pomocą żadnego z selektorów.")
        return None

    def _fill_field(self, element: WebElement, value: str, field_name: str):
        """Bezpiecznie wypełnia podany element tekstowy."""
        try:
            element.clear()
            element.send_keys(value)
            logger.info(f"Pomyślnie wypełniono pole: {field_name}.")
        except Exception as e:
            logger.error(f"Błąd podczas wypełniania pola '{field_name}': {e}")

    def _handle_terms_checkbox(self):
        """Znajduje i zaznacza checkbox, jeśli istnieje i nie jest zaznaczony."""
        try:
            checkbox = WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox']")))
            if not checkbox.is_selected():
                self.driver.execute_script("arguments[0].click();", checkbox)
                logger.info("Zaznaczono checkbox regulaminu.")
        except TimeoutException:
            logger.info("Checkbox regulaminu nie został znaleziony (krok opcjonalny).")