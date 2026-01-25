"""
Zrefaktoryzowany MedicoverClient - klasa pełniąca rolę "dyrygenta" (orchestratora),
która zarządza stanem sesji i koordynuje pracę wyspecjalizowanych komponentów.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .medicover_api import MedicoverAPI
from .medicover_authenticator import MedicoverAuthenticator
from .appointment_formatter import AppointmentFormatter
from .error_handler import AuthenticationException, RateLimitException

logger = logging.getLogger(__name__)

class LoginRequiredException(Exception):
    """Sygnalizuje, że operacja wymaga ponownego zalogowania."""
    pass
    
class MedicoverClient:
    """
    Orchestrator komponentów Medicover. Zarządza sesją użytkownika, deleguje
    zadania do authenticatora i klienta API, oraz implementuje wysokopoziomową
    logikę ponawiania prób w przypadku wygaśnięcia tokenu.
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        Inicjalizuje klienta i jego komponenty.

        Args:
            config_data: Słownik z danymi konfiguracyjnymi, w tym 'username',
                         'password' i 'headless'.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_data = config_data
        is_headless = config_data.get('headless', False)
        
        # --- Delegacja do wyspecjalizowanych komponentów ---
        self.authenticator = MedicoverAuthenticator(headless=is_headless)
        self.api = MedicoverAPI()
        self.formatter = AppointmentFormatter()
        
        # --- Zarządzanie stanem sesji ---
        self.current_token: Optional[str] = None
        
        # KLUCZOWA ZMIANA: Od razu zapisujemy dane logowania przy tworzeniu obiektu.
        # To jest niezbędne dla działania ponownego logowania po zmianie profilu.
        self.username: Optional[str] = config_data.get('username')
        self.password: Optional[str] = config_data.get('password')
        
        self.token_set_time: Optional[datetime] = None

    def login(self, username: str, password: str) -> bool:
        """
        Loguje użytkownika za pomocą authenticatora i ustawia token w kliencie API.
        Używa danych przekazanych w argumentach, a nie tych z konstruktora,
        aby umożliwić logowanie na inne dane w razie potrzeby.
        """
        progress_callback = self.config_data.get('progress_callback')
        try:
            self.authenticator = MedicoverAuthenticator(
                headless=self.config_data.get('headless', True), # Force headless usually for backend
                progress_callback=progress_callback
            )
            self.logger.info(f"Rozpoczynanie procesu logowania dla użytkownika {username}...")
            token = self.authenticator.login(username, password)
            if not token:
                self.logger.error("Uwierzytelnianie nie powiodło się: nie otrzymano tokenu.")
                return False

            if not self.api.set_bearer_token(token):
                self.logger.error("Nie udało się ustawić tokenu Bearer w kliencie API.")
                return False
            
            # Zapisanie stanu sesji po udanym logowaniu
            self.current_token = token
            # Nadpisujemy dane, aby były zgodne z ostatnim udanym logowaniem
            self.username = username
            self.password = password
            self.token_set_time = datetime.now()
            
            self.logger.info("Logowanie zakończone sukcesem.")
            return True
        except Exception as e:
            self.logger.error(f"Wystąpił krytyczny błąd podczas logowania: {e}", exc_info=True)
            return False

    def is_logged_in(self) -> bool:
        """Sprawdza, czy sesja jest aktywna na podstawie obecności i wieku tokenu."""
        if not self.current_token:
            return False
        
        # Proste sprawdzenie wieku tokenu, aby uniknąć niepotrzebnych wywołań API.
        if self.token_set_time and (datetime.now() - self.token_set_time > timedelta(minutes=45)):
            self.logger.info("Token sesji prawdopodobnie wygasł z powodu upływu czasu.")
            self._clear_token_state()
            return False
        
        return True

    def search_appointments(self, search_params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Wyszukuje wizyty. W przypadku błędu 429 (RateLimitException),
        natychmiast zwraca None, bez czekania.
        """
        final_params = self.config_data.get('search_params', {}).copy()
        if search_params:
            # Poprawka: Jeśli przekazujemy nowe SpecialtyIds, usuń stare specialty_ids
            if 'SpecialtyIds' in search_params:
                final_params.pop('specialty_ids', None)
            final_params.update(search_params)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # LAZY LOGIN: Jeśli nie jesteśmy zalogowani, spróbuj teraz
                if not self.is_logged_in():
                    if self.username and self.password:
                        self.logger.info("Sesja nieaktywna (Lazy Login). Próba automatycznego logowania...")
                        if not self._perform_relogin():
                             raise LoginRequiredException("Nie udało się zalogować automatycznie.")
                    else:
                        raise LoginRequiredException("Sesja wygasła lub nie została zainicjowana.")
                
                try:
                    # Główna próba wywołania API
                    return self.api.search_appointments(final_params)
                except RateLimitException:
                    self.logger.critical("!!! OTRZYMANO BŁĄD 429 - TWARDA BLOKADA !!!")
                    self.logger.warning("Klient informuje o błędzie 429. Zwracam None.")
                    return None # Zwróć None, aby GUI mogło wejść w kwarantannę

            except AuthenticationException as e:
                # POPRAWIONA LOGIKA: Token wygasł, próbujemy się zalogować w tle.
                self.logger.warning(f"Błąd uwierzytelnienia (próba {attempt + 1}): {e}. Próba ponownego logowania...")
                if attempt < max_retries:
                    self._clear_token_state()
                    if self._perform_relogin():
                        self.logger.info("Ponowne logowanie w tle udane. Ponawiam zapytanie do API...")
                        continue  # Wróć na początek pętli i spróbuj ponownie
                    else:
                        self.logger.error("Ponowne logowanie w tle nie powiodło się. Przerywam.")
                        # Rzuć wyjątek do GUI dopiero, gdy ponowne logowanie zawiedzie
                        raise LoginRequiredException("Nie udało się odnowić sesji.")
                else:
                    self.logger.error("Przekroczono limit prób ponownego logowania.")
                    break
            except LoginRequiredException:
                # Przekaż wyjątek dalej do GUI, jeśli został rzucony celowo
                raise
            except Exception as e:
                self.logger.error(f"Nieoczekiwany błąd w kliencie podczas wyszukiwania wizyt: {e}", exc_info=True)
                break
        
        return [] # Zwróć pustą listę, jeśli wszystkie próby zawiodły

    def book_appointment(self, appointment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rezerwuje wizytę. Używa istniejącej sesji, jeśli jest aktywna.
        NIE uruchamia Selenium automatycznie, aby nie tracić czasu, chyba że token całkowicie wygasł.
        """
        booking_string = appointment.get("bookingString")
        if not booking_string:
            return {"success": False, "error": "missing_booking_string", "message": "Brak klucza 'bookingString' w danych wizyty."}

        # SZYBKA ŚCIEŻKA: Próba rezerwacji na obecnym tokenie (bez sprawdzania czy jest logged_in, zakładamy że tak)
        if self.current_token:
            try:
                self.logger.info("Szybka rezerwacja: Próba użycia istniejącego tokenu...")
                return self.api.book_appointment(booking_string)
            except AuthenticationException:
                self.logger.warning("Szybka rezerwacja: Token wygasł. Przechodzę do pełnej procedury odnawiania.")
            except Exception as e:
                self.logger.error(f"Szybka rezerwacja: Błąd API: {e}")
                # Nie przerywamy, próbujemy standardowej ścieżki (może to jednak kwestia auth)

        # STANDARDOWA ŚCIEŻKA (ze sprawdzaniem logowania i retry)
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # LAZY LOGIN
                if not self.is_logged_in():
                    if self.username and self.password:
                        self.logger.info("Sesja nieaktywna (Lazy Login). Próba automatycznego logowania...")
                        if not self._perform_relogin():
                             raise LoginRequiredException("Nie udało się zalogować automatycznie.")
                    else:
                         raise LoginRequiredException("Sesja wygasła lub nie została zainicjowana.")
                
                return self.api.book_appointment(booking_string)
                
            except AuthenticationException as e:
                # POPRAWIONA LOGIKA: Token wygasł, próbujemy się zalogować w tle.
                self.logger.warning(f"Błąd uwierzytelnienia podczas rezerwacji (próba {attempt + 1}): {e}. Próba ponownego logowania...")
                if attempt < max_retries:
                    self._clear_token_state()
                    if self._perform_relogin():
                        self.logger.info("Ponowne uwierzytelnienie udane. Ponawianie rezerwacji...")
                        continue # Wróć na początek pętli i spróbuj ponownie
                    else:
                        self.logger.error("Ponowne logowanie w tle nie powiodło się. Przerywam rezerwację.")
                        break
                else:
                    break
            except LoginRequiredException:
                # Przekaż wyjątek dalej do GUI
                raise
            except Exception as e:
                self.logger.error(f"Nieoczekiwany błąd podczas rezerwacji: {e}", exc_info=True)
                return {"success": False, "error": "unexpected_error", "message": f"Błąd: {e}"}

        return {"success": False, "error": "authentication_failed", "message": "Rezerwacja nie powiodła się z powodu błędu uwierzytelnienia."}

    def _clear_token_state(self) -> None:
        """Scentralizowana metoda do czyszczenia stanu tokenu."""
        self.logger.debug("Czyszczenie stanu tokenu sesji.")
        self.current_token = None
        self.token_set_time = None
        self.api.clear_token()

    def _perform_relogin(self) -> bool:
        """
        Prywatna metoda do wykonania ponownego logowania w tle.
        Używa danych logowania przechowywanych w instancji klienta.
        """
        self.logger.info("Próba wykonania ponownego logowania w tle...")
        if not self.username or not self.password:
            self.logger.error("Brak zapisanych danych logowania do ponownego uwierzytelnienia.")
            return False
        
        # Wywołaj główną metodę logowania z zapisanymi danymi
        return self.login(self.username, self.password)
    def close(self):
        """Zamyka przeglądarkę zarządzaną przez authenticator."""
        self.logger.info("Zamykanie zasobów klienta (przeglądarka)...")
        self.authenticator.close()

    def format_appointment_details(self, appointment: Dict[str, Any]) -> str:
        """Deleguje formatowanie szczegółów wizyty do formattera."""
        return self.formatter.format_details(appointment)

    def get_session_info(self) -> Dict[str, Any]:
        """Zbiera i zwraca informacje diagnostyczne o sesji."""
        token_age = None
        if self.token_set_time:
            token_age = int((datetime.now() - self.token_set_time).total_seconds())

        return {
            "is_logged_in": self.is_logged_in(),
            "has_bearer_token": bool(self.current_token),
            "token_age_seconds": token_age,
            "authenticator_info": self.authenticator.get_auth_info(),
            "api_session_info": self.api.get_session_info()
        }
