""" 
Zrefaktoryzowany MedicoverClient - klasa pełniąca rolę "dyrygenta" (orchestratora),
która zarządza stanem sesji i koordynuje pracę wyspecjalizowanych komponentów.

WERSJA: Obsługa tokenów per profil (izolacja stanu) + kompatybilność wsteczna.

Wymagania:
- token w pamięci procesu per profil
- deterministyczny TTL ~8.5 min
- logi per request: profile_id, token_age_s, expires_in_s, token_hash_prefix
- relogin tylko dla profilu, którego dotyczy
"""

import logging
import threading
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from .medicover_api import MedicoverAPI
from .medicover_authenticator import MedicoverAuthenticator
from .appointment_formatter import AppointmentFormatter
from .error_handler import AuthenticationException, RateLimitException

logger = logging.getLogger(__name__)


class LoginRequiredException(Exception):
    """Sygnalizuje, że operacja wymaga ponownego zalogowania."""


class MedicoverClient:
    """Orchestrator komponentów Medicover. Zarządza sesją użytkownika PER PROFIL."""

    # Deterministyczny czas życia tokenu (z logów ~510s ≈ 8m30s)
    TOKEN_TTL_SECONDS = 510

    # Odświeżamy zanim dobijemy do expiry, żeby uniknąć 401
    REFRESH_BUFFER_SECONDS = 75

    def __init__(self, config_data: Dict[str, Any]):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_data = config_data
        is_headless = config_data.get("headless", False)

        self.authenticator = MedicoverAuthenticator(headless=is_headless)
        self.api = MedicoverAPI()
        self.formatter = AppointmentFormatter()

        # Domyślny profil dla kompatybilności (gdy reszta aplikacji nie przekazuje profile_id)
        self.default_profile_id: int = int(config_data.get("profile_id", 0) or 0)

        # --- Zarządzanie stanem sesji PER PROFIL ---
        # Struktura: { profile_id: { token, issued_at, expires_at, last_refresh_at, username, password } }
        self._tokens_by_profile: Dict[int, Dict[str, Any]] = {}
        self._tokens_lock = threading.RLock()

        # Domyślne credentials (fallback)
        self.default_username: Optional[str] = config_data.get("username")
        self.default_password: Optional[str] = config_data.get("password")

    # -----------------------------
    # Backward compatibility layer
    # -----------------------------

    @property
    def current_token(self) -> Optional[str]:
        """Wsteczna kompatybilność: zwraca token dla default_profile_id."""
        return self.get_token(self.default_profile_id)

    @current_token.setter
    def current_token(self, token: Optional[str]) -> None:
        """Wsteczna kompatybilność: ustawia/usuwa token dla default_profile_id."""
        profile_id = self.default_profile_id
        if not token:
            with self._tokens_lock:
                self._tokens_by_profile.pop(profile_id, None)
            return

        username, password = self._get_credentials_for_profile(profile_id)
        if not username or not password:
            self.logger.error(
                f"Nie można ustawić current_token bez credentials (profile_id={profile_id})."
            )
            return

        self._set_token_entry(profile_id, token, username, password)

    @property
    def token_set_time(self) -> Optional[datetime]:
        """Wsteczna kompatybilność: czas ustawienia tokenu dla default_profile_id."""
        entry = self._get_token_entry(self.default_profile_id)
        return entry.get("issued_at") if entry else None

    # -----------------------------
    # Token helpers
    # -----------------------------

    def _token_hash_prefix(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:6]

    def _get_token_entry(self, profile_id: int) -> Optional[Dict[str, Any]]:
        with self._tokens_lock:
            return self._tokens_by_profile.get(int(profile_id))

    def _get_credentials_for_profile(self, profile_id: int) -> Tuple[Optional[str], Optional[str]]:
        entry = self._get_token_entry(profile_id)
        if entry and entry.get("username") and entry.get("password"):
            return entry.get("username"), entry.get("password")
        return self.default_username, self.default_password

    def _set_token_entry(self, profile_id: int, token: str, username: str, password: str) -> None:
        now = datetime.now()
        expires_at = now + timedelta(seconds=self.TOKEN_TTL_SECONDS)
        token_hash_prefix = self._token_hash_prefix(token)

        with self._tokens_lock:
            self._tokens_by_profile[int(profile_id)] = {
                "token": token,
                "username": username,
                "password": password,
                "issued_at": now,
                "last_refresh_at": now,
                "expires_at": expires_at,
                "token_hash_prefix": token_hash_prefix,
            }

        self.logger.info(
            f"Token updated profile_id={profile_id} token_hash_prefix={token_hash_prefix} "
            f"expires_at={expires_at.isoformat()}"
        )

    def _clear_token_entry(self, profile_id: int) -> None:
        with self._tokens_lock:
            self._tokens_by_profile.pop(int(profile_id), None)

    def _log_token_usage(self, profile_id: int, entry: Dict[str, Any]) -> None:
        age_s = int((datetime.now() - entry["issued_at"]).total_seconds())
        expires_in_s = int((entry["expires_at"] - datetime.now()).total_seconds())
        token_hash_prefix = entry.get("token_hash_prefix") or "unknown"
        self.logger.info(
            f"request profile_id={profile_id} token_age_s={age_s} expires_in_s={expires_in_s} "
            f"token_hash_prefix={token_hash_prefix}"
        )

    def _ensure_valid_token(self, profile_id: int, reason: str) -> str:
        """Zwraca ważny token dla profilu; w razie potrzeby odświeża (tylko dla tego profilu)."""
        profile_id = int(profile_id)
        entry = self._get_token_entry(profile_id)

        if not entry:
            self.logger.info(f"relogin profile_id={profile_id} reason=missing age_s=0")
            if not self._perform_relogin(profile_id):
                raise LoginRequiredException(f"Brak sesji dla profilu {profile_id}.")
            entry = self._get_token_entry(profile_id)
            if not entry:
                raise LoginRequiredException(f"Brak tokenu po relogin (profil {profile_id}).")

        age_s = int((datetime.now() - entry["issued_at"]).total_seconds())
        expires_in_s = int((entry["expires_at"] - datetime.now()).total_seconds())

        if expires_in_s <= self.REFRESH_BUFFER_SECONDS:
            self.logger.info(
                f"relogin profile_id={profile_id} reason=expires_soon({reason}) age_s={age_s}"
            )
            if not self._perform_relogin(profile_id):
                raise LoginRequiredException(
                    f"Nie udało się odświeżyć sesji dla profilu {profile_id}."
                )
            entry = self._get_token_entry(profile_id)
            if not entry:
                raise LoginRequiredException(f"Brak tokenu po refresh (profil {profile_id}).")

        # Log per request (wymaganie)
        self._log_token_usage(profile_id, entry)
        return entry["token"]

    # -----------------------------
    # Public API
    # -----------------------------

    def login(self, username: str, password: str, profile_id: Optional[int] = None) -> bool:
        """Loguje użytkownika i zapisuje token dla danego profilu."""
        if profile_id is None:
            profile_id = self.default_profile_id

        progress_callback = self.config_data.get("progress_callback")
        try:
            self.authenticator = MedicoverAuthenticator(
                headless=self.config_data.get("headless", True),
                progress_callback=progress_callback,
            )

            self.logger.info(
                f"Rozpoczynanie logowania dla profilu {profile_id} (użytkownik {username})..."
            )

            token = self.authenticator.login(username, password)
            if not token:
                self.logger.error(f"Logowanie nieudane dla profilu {profile_id}.")
                return False

            self._set_token_entry(profile_id, token, username, password)
            self.logger.info(f"Logowanie zakończone sukcesem dla profilu {profile_id}.")
            return True
        except Exception as e:
            self.logger.error(
                f"Krytyczny błąd logowania (profil {profile_id}): {e}", exc_info=True
            )
            return False

    def is_logged_in(self, profile_id: Optional[int] = None) -> bool:
        """Sprawdza ważność tokenu dla konkretnego profilu."""
        if profile_id is None:
            profile_id = self.default_profile_id

        entry = self._get_token_entry(profile_id)
        if not entry:
            return False

        if datetime.now() > entry["expires_at"]:
            self.logger.info(f"Token dla profilu {profile_id} wygasł (expires_at).")
            self._clear_token_entry(profile_id)
            return False

        return True

    def get_token(self, profile_id: Optional[int] = None) -> Optional[str]:
        """Zwraca token dla profilu (bez wymuszania refresh)."""
        if profile_id is None:
            profile_id = self.default_profile_id

        entry = self._get_token_entry(profile_id)
        if not entry:
            return None

        age_s = int((datetime.now() - entry["issued_at"]).total_seconds())
        expires_in_s = int((entry["expires_at"] - datetime.now()).total_seconds())
        token_hash_prefix = entry.get("token_hash_prefix") or "unknown"

        self.logger.info(
            f"Using token profile_id={profile_id} token_age_s={age_s} expires_in_s={expires_in_s} "
            f"token_hash_prefix={token_hash_prefix}"
        )
        return entry["token"]

    def search_appointments(
        self, search_params: Optional[Dict[str, Any]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        final_params = self.config_data.get("search_params", {}).copy()
        if search_params:
            if "SpecialtyIds" in search_params:
                final_params.pop("specialty_ids", None)
            final_params.update(search_params)

        profile_id = int(final_params.get("profile_id", self.default_profile_id))

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                token = self._ensure_valid_token(profile_id, reason="search")

                try:
                    return self.api.search_appointments(final_params, token)
                except RateLimitException:
                    self.logger.critical("!!! OTRZYMANO BŁĄD 429 - TWARDA BLOKADA !!!")
                    return None

            except AuthenticationException:
                # 401 - token odrzucony przez API, odświeżamy TYLKO ten profil
                entry = self._get_token_entry(profile_id)
                age_s = (
                    int((datetime.now() - entry["issued_at"]).total_seconds()) if entry else 0
                )
                self.logger.info(
                    f"relogin profile_id={profile_id} reason=401 age_s={age_s}"
                )
                self._clear_token_entry(profile_id)

                if attempt < max_retries:
                    if self._perform_relogin(profile_id):
                        continue
                    raise LoginRequiredException("Nie udało się odnowić sesji.")
                break
            except LoginRequiredException:
                raise
            except Exception as e:
                self.logger.error(
                    f"Nieoczekiwany błąd (profil {profile_id}): {e}", exc_info=True
                )
                break

        return []

    def book_appointment(self, appointment: Dict[str, Any], profile_id: Optional[int] = None) -> Dict[str, Any]:
        if profile_id is None:
            profile_id = self.default_profile_id

        booking_string = appointment.get("bookingString")
        if not booking_string:
            return {
                "success": False,
                "error": "missing_booking_string",
                "message": "Brak klucza 'bookingString'.",
            }

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                token = self._ensure_valid_token(profile_id, reason="book")
                return self.api.book_appointment(booking_string, token)

            except AuthenticationException:
                entry = self._get_token_entry(profile_id)
                age_s = (
                    int((datetime.now() - entry["issued_at"]).total_seconds()) if entry else 0
                )
                self.logger.info(
                    f"relogin profile_id={profile_id} reason=401 age_s={age_s}"
                )
                self._clear_token_entry(profile_id)

                if attempt < max_retries:
                    if self._perform_relogin(profile_id):
                        continue
                return {
                    "success": False,
                    "error": "auth_failed",
                    "message": "Nieudane odświeżenie sesji.",
                }
            except LoginRequiredException as e:
                return {"success": False, "error": "auth_required", "message": str(e)}
            except Exception as e:
                return {"success": False, "error": "unexpected", "message": str(e)}

        return {"success": False, "error": "auth_failed", "message": "Błąd uwierzytelnienia."}

    def _perform_relogin(self, profile_id: Optional[int] = None) -> bool:
        """Loguje ponownie konkretny profil używając zapisanych credentials."""
        if profile_id is None:
            profile_id = self.default_profile_id

        username, password = self._get_credentials_for_profile(profile_id)
        if not username or not password:
            self.logger.error(f"Brak danych logowania dla profilu {profile_id}.")
            return False

        return self.login(username, password, profile_id)

    def close(self) -> None:
        self.authenticator.close()

    def format_appointment_details(self, appointment: Dict[str, Any]) -> str:
        return self.formatter.format_details(appointment)

    def get_session_info(self) -> Dict[str, Any]:
        profiles_info = []
        with self._tokens_lock:
            for pid, data in self._tokens_by_profile.items():
                age = int((datetime.now() - data["issued_at"]).total_seconds())
                expires = int((data["expires_at"] - datetime.now()).total_seconds())
                profiles_info.append(
                    {
                        "profile_id": pid,
                        "age_seconds": age,
                        "expires_in_seconds": expires,
                        "token_hash_prefix": data.get("token_hash_prefix"),
                    }
                )

        return {
            "default_profile_id": self.default_profile_id,
            "active_profiles_count": len(profiles_info),
            "profiles": profiles_info,
            "api_stateless": True,
        }
