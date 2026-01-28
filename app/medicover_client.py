"""
Zrefaktoryzowany MedicoverClient - klasa pełniąca rolę "dyrygenta" (orchestratora),
która zarządza stanem sesji i koordynuje pracę wyspecjalizowanych komponentów.
WERSJA: Obsługa tokenów per profil (izolacja stanu).
"""

import logging
import threading
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
    Orchestrator komponentów Medicover. Zarządza sesją użytkownika PER PROFIL.
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        Inicjalizuje klienta.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_data = config_data
        is_headless = config_data.get('headless', False)
        
        self.authenticator = MedicoverAuthenticator(headless=is_headless)
        self.api = MedicoverAPI()
        self.formatter = AppointmentFormatter()
        
        # --- Zarządzanie stanem sesji PER PROFIL ---
        # Struktura: { profile_id (int): { 'token': str, 'expires_at': datetime, 'creds': (user, pass) } }
        self._tokens_by_profile: Dict[int, Dict[str, Any]] = {}
        self._tokens_lock = threading.RLock() # Zabezpieczenie dla wątków
        
        # Domyślne credentials (dla wstecznej kompatybilności lub fallback)
        self.default_username: Optional[str] = config_data.get('username')
        self.default_password: Optional[str] = config_data.get('password')

    def _get_token_entry(self, profile_id: int) -> Optional[Dict[str, Any]]:
        with self._tokens_lock:
            return self._tokens_by_profile.get(profile_id)

    def _set_token_entry(self, profile_id: int, token: str, username: str, password: str):
        with self._tokens_lock:
            self._tokens_by_profile[profile_id] = {
                'token': token,
                'username': username,
                'password': password,
                'token_set_time': datetime.now(),
                'expires_at': datetime.now() + timedelta(minutes=45) # Bezpieczny czas życia
            }
            self.logger.info(f"Zapisano token dla profilu {profile_id}. Wygasa: {self._tokens_by_profile[profile_id]['expires_at']}")

    def login(self, username: str, password: str, profile_id: Optional[int] = None) -> bool:
        """
        Loguje użytkownika i zapisuje token dla danego profilu.
        Jeśli profile_id nie jest podany, próbuje go zgadnąć lub używa 0 (legacy).
        """
        # Jeśli brak profile_id, używamy 0 jako "global/default"
        if profile_id is None:
            profile_id = 0 
            
        progress_callback = self.config_data.get('progress_callback')
        try:
            # Re-init authenticator for clean state
            self.authenticator = MedicoverAuthenticator(
                headless=self.config_data.get('headless', True),
                progress_callback=progress_callback
            )
            self.logger.info(f"Rozpoczynanie logowania dla profilu {profile_id} (użytkownik {username})...")
            
            token = self.authenticator.login(username, password)
            if not token:
                self.logger.error(f"Logowanie nieudane dla profilu {profile_id}.")
                return False

            # Zapisz token w mapie per profil
            self._set_token_entry(profile_id, token, username, password)
            
            self.logger.info(f"Logowanie zakończone sukcesem dla profilu {profile_id}.")
            return True
        except Exception as e:
            self.logger.error(f"Krytyczny błąd logowania (profil {profile_id}): {e}", exc_info=True)
            return False

    def is_logged_in(self, profile_id: int = 0) -> bool:
        """Sprawdza ważność tokenu dla konkretnego profilu."""
        entry = self._get_token_entry(profile_id)
        if not entry:
            return False
        
        if datetime.now() > entry['expires_at']:
            self.logger.info(f"Token dla profilu {profile_id} wygasł (czas życia).")
            with self._tokens_lock:
                self._tokens_by_profile.pop(profile_id, None)
            return False
        
        return True

    def get_token(self, profile_id: int) -> Optional[str]:
        """Zwraca czysty string tokenu lub None."""
        entry = self._get_token_entry(profile_id)
        if entry:
            age = (datetime.now() - entry['token_set_time']).total_seconds()
            expires_in = (entry['expires_at'] - datetime.now()).total_seconds()
            self.logger.info(f"Using token profile={profile_id} age={int(age)}s expires_in={int(expires_in)}s")
            return entry['token']
        return None

    def search_appointments(self, search_params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Wyszukuje wizyty. Wymaga profile_id w search_params (lub używa default 0).
        """
        final_params = self.config_data.get('search_params', {}).copy()
        if search_params:
            if 'SpecialtyIds' in search_params:
                final_params.pop('specialty_ids', None)
            final_params.update(search_params)

        # Wyciągnij profile_id
        profile_id = final_params.get('profile_id', 0)
        # Usuń z params żeby nie leciało do API (MedicoverAPI już to też czyści, ale dla porządku)
        # Nie usuwamy tutaj, bo MedicoverAPI.build_params to obsłuży, a może się przydać do debugu.

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # 1. Pobierz token
                token = self.get_token(profile_id)
                
                # 2. Lazy Login jeśli brak tokenu
                if not token:
                    # Spróbuj odzyskać credentials z configu jeśli to pierwszy run,
                    # albo z mapy tokenów (ale tam ich nie ma bo nie ma tokenu),
                    # więc bierzemy z self.default_* jeśli pasuje, albo rzucamy błąd.
                    # W idealnym świecie frontend powinien wymusić login.
                    
                    user = self.default_username
                    pwd = self.default_password
                    
                    # Jeśli w mapie były stare credentials, może warto ich użyć?
                    # Ale skoro nie ma entry, to nie ma credentials.
                    
                    if user and pwd:
                        self.logger.info(f"Brak tokenu dla profilu {profile_id}. Próba autologowania (Lazy Login)...")
                        if not self.login(user, pwd, profile_id):
                             raise LoginRequiredException("Nie udało się zalogować automatycznie.")
                        token = self.get_token(profile_id) # Pobierz nowy token
                    else:
                        raise LoginRequiredException(f"Brak sesji dla profilu {profile_id} i brak danych logowania.")

                try:
                    # 3. Wywołanie API z tokenem
                    return self.api.search_appointments(final_params, token)
                except RateLimitException:
                    self.logger.critical("!!! OTRZYMANO BŁĄD 429 - TWARDA BLOKADA !!!")
                    return None

            except AuthenticationException as e:
                self.logger.warning(f"Token profilu {profile_id} odrzucony (401). Próba odnowienia...")
                
                # Wyczyść stary token
                with self._tokens_lock:
                    self._tokens_by_profile.pop(profile_id, None)
                
                if attempt < max_retries:
                    if self._perform_relogin(profile_id):
                        self.logger.info("Relogin udany. Ponawiam zapytanie...")
                        continue
                    else:
                        raise LoginRequiredException("Nie udało się odnowić sesji.")
                else:
                    break
            except LoginRequiredException:
                raise
            except Exception as e:
                self.logger.error(f"Nieoczekiwany błąd (profil {profile_id}): {e}", exc_info=True)
                break
        
        return []

    def book_appointment(self, appointment: Dict[str, Any], profile_id: int = 0) -> Dict[str, Any]:
        """
        Rezerwuje wizytę dla konkretnego profilu.
        """
        booking_string = appointment.get("bookingString")
        if not booking_string:
            return {"success": False, "error": "missing_booking_string", "message": "Brak klucza 'bookingString'."}

        # 1. Szybka ścieżka na istniejącym tokenie
        token = self.get_token(profile_id)
        if token:
            try:
                return self.api.book_appointment(booking_string, token)
            except AuthenticationException:
                pass # Fallback do retry loop
            except Exception as e:
                # Inne błędy API
                 return {"success": False, "error": "api_error", "message": str(e)}

        # 2. Pełna ścieżka z retry
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                token = self.get_token(profile_id)
                if not token:
                    if self._perform_relogin(profile_id):
                        token = self.get_token(profile_id)
                    else:
                        raise LoginRequiredException("Brak sesji.")

                return self.api.book_appointment(booking_string, token)
                
            except AuthenticationException:
                # Wyczyść i ponów
                with self._tokens_lock:
                    self._tokens_by_profile.pop(profile_id, None)
                
                if attempt < max_retries:
                    if self._perform_relogin(profile_id):
                        continue
                return {"success": False, "error": "auth_failed", "message": "Nieudane odświeżenie sesji."}
            except Exception as e:
                 return {"success": False, "error": "unexpected", "message": str(e)}

        return {"success": False, "error": "auth_failed", "message": "Błąd uwierzytelnienia."}

    def _perform_relogin(self, profile_id: int = 0) -> bool:
        """Loguje ponownie konkretny profil używając zapisanych credentials."""
        # Spróbuj znaleźć credentials w wygasłym wpisie (jeśli jeszcze jest)
        # lub użyj domyślnych
        
        entry = self._get_token_entry(profile_id)
        username = entry.get('username') if entry else self.default_username
        password = entry.get('password') if entry else self.default_password
        
        if not username or not password:
            self.logger.error(f"Brak danych logowania dla profilu {profile_id}.")
            return False
            
        return self.login(username, password, profile_id)

    def close(self):
        self.authenticator.close()

    def format_appointment_details(self, appointment: Dict[str, Any]) -> str:
        return self.formatter.format_details(appointment)

    def get_session_info(self) -> Dict[str, Any]:
        """Info diagnostyczne dla wszystkich profili."""
        profiles_info = []
        with self._tokens_lock:
            for pid, data in self._tokens_by_profile.items():
                age = (datetime.now() - data['token_set_time']).total_seconds()
                expires = (data['expires_at'] - datetime.now()).total_seconds()
                profiles_info.append({
                    "profile_id": pid,
                    "age_seconds": int(age),
                    "expires_in_seconds": int(expires)
                })
                
        return {
            "active_profiles_count": len(profiles_info),
            "profiles": profiles_info,
            "api_stateless": True
        }