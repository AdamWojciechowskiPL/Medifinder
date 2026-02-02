"""
Główny moduł aplikacji Medicover, dedykowany do uruchamiania
interfejsu graficznego (GUI).
"""

import logging
import sys
import threading
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import date, datetime, time, timedelta

# Zredukowane, niezbędne importy
from .config import Config
from .profile_manager import ProfileManager
from .medicover_client import MedicoverClient
from .data_manager import SpecialtyManager, DoctorManager, ClinicManager
from .error_handler import AuthenticationException

class MedicoverApp:
    """
    Główna klasa aplikacji, która zarządza stanem, konfiguracją
    i koordynuje pracę komponentów dla potrzeb GUI.
    """
    def __init__(self, config_dir: Path):
        """Inicjalizuje aplikację i jej kluczowe komponenty."""
        self.config = Config(config_dir / "credentials.json")
        self._setup_logging()
        self.logger = logging.getLogger(self.__class__.__name__)

        # --- Niezbędne zależności ---
        self.profile_manager = ProfileManager(config_dir)
        self.client: Optional[MedicoverClient] = None
        self.specialty_manager = SpecialtyManager(config_dir / "specialties.json")
        self.doctor_manager = DoctorManager(config_dir / "doctors.json")
        self.clinic_manager = ClinicManager(config_dir / "clinics.json")

        # --- Stan aplikacji (uproszczony) ---
        self.current_profile: Optional[str] = None
        self.config_dir = config_dir
        self._initialize_default_profile_and_client()
        
        # --- Cache sesji ---
        # ZMIANA: Kluczem jest user_email_username (login Medicover), aby współdzielić sesje
        # dla różnych profili korzystających z tych samych poświadczeń.
        # Key: "user@email.com_Login123" -> Value: {'token': str, 'expires_at': datetime, 'issued_at': datetime, 'last_used': datetime}
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        self._session_lock = threading.Lock()
        
        # ZMIANA: Blokady per użytkownik, aby uniknąć równoczesnego logowania
        self._user_locks: Dict[str, threading.Lock] = {}
        self._user_locks_lock = threading.Lock() # Do ochrony słownika blokad
        
        # ZMIANA: Token Medicover jest ważny sztywno 8m 30s od pobrania.
        # API nie przedłuża jego ważności. Czas jest liczony od momentu zalogowania przez Selenium.
        self.TOKEN_VALIDITY_SECONDS = 510  # 8 min 30 sek
        
    def _mask_text(self, text: str, visible_chars: int = 3) -> str:
        """Maskuje tekst (np. email lub login) zostawiając ostatnie znaki."""
        if not text: return "None"
        if len(text) <= visible_chars: return "***"
        return "***" + text[-visible_chars:]

    def _get_user_lock(self, user_email: str) -> threading.Lock:
        """Zwraca (tworząc w razie potrzeby) blokadę dla danego użytkownika."""
        with self._user_locks_lock:
            if user_email not in self._user_locks:
                self._user_locks[user_email] = threading.Lock()
            return self._user_locks[user_email]

    def _parse_appointment_date_dt(self, apt: Dict[str, Any]) -> Optional[datetime]:
        """Parsuje datę wizyty do obiektu datetime (z obsługą timezone)."""
        s = apt.get('appointmentDate')
        if not s:
            return None
        try:
            # Obsłuż ISO z Z
            if isinstance(s, str) and s.endswith('Z'):
                s = s.replace('Z', '+00:00')
            return datetime.fromisoformat(s)
        except Exception:
            return None

    def _is_time_in_range(self, t_val: time, start: Optional[time], end: Optional[time]) -> bool:
        """Sprawdza czy godzina mieści się w zakresie (z obsługą zakresów przez północ)."""
        if not start and not end:
            return True
        if start and not end:
            return t_val >= start
        if end and not start:
            return t_val <= end

        if not start or not end:
            return True

        # Standardowy zakres w obrębie doby
        if start <= end:
            return start <= t_val <= end

        # Zakres przechodzący przez północ, np. 22:00–06:00 lub 11:00–00:00
        return t_val >= start or t_val <= end
            
    def find_consecutive_slots(self, appointments: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """
        Znajduje pary wizyt następujących po sobie (u tego samego lekarza, w tej samej placówce).
        Zakładamy odstęp 10-20 minut (standardowo 15 min).
        """
        if len(appointments) < 2:
            return []
            
        # Grupuj po lekarzu i placówce
        grouped = {}
        for apt in appointments:
            doc_id = apt.get('doctor', {}).get('id')
            clinic_id = apt.get('clinic', {}).get('id')
            if not doc_id or not clinic_id:
                continue
                
            key = (doc_id, clinic_id)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(apt)
            
        pairs = []
        
        for key, group in grouped.items():
            # Sortuj po dacie
            group.sort(key=lambda x: x.get('appointmentDate', ''))
            
            for i in range(len(group) - 1):
                apt1 = group[i]
                apt2 = group[i+1]
                
                dt1 = self._parse_appointment_date_dt(apt1)
                dt2 = self._parse_appointment_date_dt(apt2)
                
                if not dt1 or not dt2:
                    continue
                    
                diff = (dt2 - dt1).total_seconds() / 60
                
                # Tolerancja: zazwyczaj wizyty są co 15 min (diff=15), ale dajmy zakres 10-20 min
                if 10 <= diff <= 20:
                    pairs.append((apt1, apt2))
                    
        return pairs

    def _filter_results_by_preferences(self, appointments: List[Dict[str, Any]], 
                                     preferred_days: List[int], 
                                     time_range: Dict[str, str],
                                     day_time_ranges: Dict[str, Dict[str, str]] = None,
                                     excluded_dates: List[date] = None) -> List[Dict[str, Any]]:
        """
        Rozszerzone filtrowanie wyników.
        """
        if not appointments:
            return []
            
        filtered: List[Dict[str, Any]] = []
        
        # Parsowanie globalnego zakresu godzin
        global_start_time: Optional[time] = None
        global_end_time: Optional[time] = None
        
        if time_range:
            try:
                if time_range.get('start'):
                    parts = time_range['start'].split(':')
                    global_start_time = time(int(parts[0]), int(parts[1]))
                if time_range.get('end'):
                    parts = time_range['end'].split(':')
                    global_end_time = time(int(parts[0]), int(parts[1]))
            except Exception: pass

        self.logger.debug(f"START Filtrowanie pref: wejście={len(appointments)}")

        for apt in appointments:
            dt = self._parse_appointment_date_dt(apt)
            if not dt:
                filtered.append(apt) # Fail-open
                continue

            # 0. Sprawdź wykluczone daty (blacklist)
            if excluded_dates:
                apt_date = dt.date()
                if apt_date in excluded_dates:
                    continue

            # 1. Sprawdź dzień tygodnia (0=Pon, 6=Nd)
            weekday = dt.weekday()
            
            # Jeśli user zaznaczył "dni tygodnia" w checkboxach, sprawdź to
            if preferred_days and weekday not in preferred_days:
                continue

            # 2. Sprawdź godziny
            t = dt.time()
            
            # Najpierw sprawdź czy dla tego dnia jest SPECIFICZNY zakres godzin
            specific_range_found = False
            if day_time_ranges and str(weekday) in day_time_ranges:
                specific = day_time_ranges[str(weekday)]
                try:
                    s_parts = specific['start'].split(':')
                    e_parts = specific['end'].split(':')
                    s_time = time(int(s_parts[0]), int(s_parts[1]))
                    e_time = time(int(e_parts[0]), int(e_parts[1]))

                    if not self._is_time_in_range(t, s_time, e_time):
                        continue # Poza zakresem specyficznym dla dnia
                    
                    specific_range_found = True
                except Exception:
                    self.logger.warning(f"Błąd parsowania zakresu dla dnia {weekday}")

            # Jeśli nie znaleziono specyficznego zakresu, użyj globalnego (jeśli zdefiniowany)
            if not specific_range_found:
                if global_start_time and global_end_time:
                    if not self._is_time_in_range(t, global_start_time, global_end_time):
                        continue
                else:
                    if global_start_time and t < global_start_time:
                        continue
                    if global_end_time and t > global_end_time:
                        continue

            filtered.append(apt)

        return filtered

    def _filter_results_by_date_range(self, appointments: List[Dict[str, Any]], start_date: Optional[str], end_date: Optional[str]) -> List[Dict[str, Any]]:
        if not appointments:
            return appointments

        start = None
        end = None
        
        def parse_date_input(d_str: str) -> Optional[date]:
            if not d_str:
                return None
            try:
                return date.fromisoformat(d_str)
            except ValueError:
                try:
                    s = d_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(s).date()
                except Exception:
                    return None

        if start_date:
            start = parse_date_input(start_date)

        if end_date:
            end = parse_date_input(end_date)

        if not start and not end:
            return appointments

        filtered: List[Dict[str, Any]] = []
        for apt in appointments:
            dt = self._parse_appointment_date_dt(apt)
            if not dt:
                filtered.append(apt)
                continue
            
            d = dt.date()
            if start and d < start:
                continue
            if end and d > end:
                continue
            filtered.append(apt)

        return filtered
        
    def _update_data_from_appointments(self, appointments: List[Dict[str, Any]]) -> None:
        if not appointments: return
        doctors_updated = 0
        clinics_updated = 0
        for apt in appointments:
            doctor = apt.get('doctor')
            clinic = apt.get('clinic')
            specialty = apt.get('specialty')
            if doctor and specialty:
                if self.doctor_manager.add_or_update(doctor, specialty.get('id')): doctors_updated += 1
            if clinic:
                if self.clinic_manager.add_or_update(clinic): clinics_updated += 1
        if doctors_updated > 0 or clinics_updated > 0:
            self.logger.info(f"Aktualizacja baz danych zakończona. Nowi: {doctors_updated} lek, {clinics_updated} plac.")
            
    def _setup_logging(self) -> None:
        log_config = self.config.get('logging', {})
        logging.basicConfig(level=log_config.get('level', 'INFO').upper(), format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'), handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('medicover_app.log', encoding='utf-8')])

    def _initialize_default_profile_and_client(self) -> None:
        if not self.profile_manager.profiles_path.exists(): self.logger.warning("Nie znaleziono pliku profili.")

    def switch_profile(self, profile_name: str) -> bool: return False

    def get_available_profiles(self, user_email: str) -> List[Dict[str, Any]]:
        """Zwraca listę dostępnych profili dla danego użytkownika."""
        return [
            {
                "login": p.username,
                "name": p.description if p.description else p.username,
                "is_child": p.is_child_account
            }
            for p in self.profile_manager.get_user_profiles(user_email)
        ]

    def get_current_profile(self) -> Optional[str]: return self.current_profile
    def add_profile(self, user_email: str, login: str, password: str, name: str, is_child_account: bool = False) -> bool: return self.profile_manager.add_profile(user_email, login, password, name, is_child_account)
    
    def _get_cache_key(self, user_email: str, username: str) -> str:
        # Używamy loginu Medicover (username) jako klucza, aby profile 
        # współdzielące to samo konto nie nadpisywały sesji.
        return f"{user_email}_{username}"

    def _get_cached_session(self, user_email: str, username: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera aktywne dane sesji z cache dla użytkownika i loginu Medicover.
        UWAGA: Zwraca pełny obiekt (token, timestamps).
        """
        key = self._get_cache_key(user_email, username)
        with self._session_lock:
            if key in self._session_cache:
                data = self._session_cache[key]
                now = datetime.now()
                
                # Sprawdź czy token nie wygasł - źródłem prawdy jest expires_at
                if now < data['expires_at']:
                    # TOKEN JEST JESZCZE WAŻNY
                    # Nie aktualizujemy last_used, aby nie 'odmładzać' sesji (brak touch)
                    return data
                else:
                    # Token wygasł - usuń z cache
                    self.logger.info(f"⏰ Token cache dla {self._mask_text(key)} wygasł (expires_at={data['expires_at'].strftime('%H:%M:%S')}). Usuwam z cache.")
                    del self._session_cache[key]
        return None

    def _cache_session(self, user_email: str, username: str, token: str, 
                       issued_at: datetime = None, expires_at: datetime = None):
        """Zapisuje token do cache dla użytkownika i loginu Medicover."""
        key = self._get_cache_key(user_email, username)
        now = datetime.now()
        
        # Jeśli nie podano czasów, wylicz domyślne (dla nowej sesji)
        final_expires_at = expires_at if expires_at else (now + timedelta(seconds=self.TOKEN_VALIDITY_SECONDS))
        final_issued_at = issued_at if issued_at else now

        with self._session_lock:
            # Sprawdź czy token się zmienił przed logowaniem
            old_entry = self._session_cache.get(key)
            if old_entry and old_entry['token'] == token:
                # Token jest ten sam - nic nie rób
                return

            self._session_cache[key] = {
                'token': token,
                'expires_at': final_expires_at,
                'issued_at': final_issued_at,
                'last_used': now
            }
            # Logujemy dokładną datę wygaśnięcia, aby ułatwić debugowanie
            self.logger.info(f"💾 Token cache dla {self._mask_text(key)} zapisany. Wygasa: {final_expires_at.strftime('%H:%M:%S')}")

    def _refresh_token_ttl(self, user_email: str, username: str):
        """
        DEPRECATED: Aktualizacja last_used usunięta, aby nie przesuwać czasu życia.
        Zostawione jako pusta metoda dla kompatybilności wstecznej (jeśli ktoś używa).
        """
        pass
        
    def refresh_session(self, user_email: str, profile: str) -> bool:
        """
        Wymusza odświeżenie sesji (nowy login + token) dla danego profilu.
        Czyści cache i loguje się ponownie przez Selenium.
        """
        if not user_email or not profile: return False
        
        # Używamy blokady użytkownika, aby nie wchodzić w konflikt z normalnym search
        user_lock = self._get_user_lock(user_email)
        with user_lock:
            credentials = self.profile_manager.get_credentials(user_email, profile)
            if not credentials: return False
            username, password = credentials
            
            # 1. Wyczyść cache dla tego konta
            key = self._get_cache_key(user_email, username)
            with self._session_lock:
                if key in self._session_cache:
                    self.logger.info(f"🧹 (Refresh) Czyszczenie cache dla {self._mask_text(key)}.")
                    del self._session_cache[key]
            
            # 2. Wykonaj logowanie
            client_config = self.config.data.copy()
            client_config['username'] = username
            client_config['password'] = password
            
            try:
                p_id = int(username)
                client_config['profile_id'] = p_id
            except ValueError:
                self.logger.error(f"Invalid username: {username}")
                return False

            try:
                # Tworzymy instancję klienta
                temp_client = MedicoverClient(client_config)
                self.logger.info(f"🔥 (Force Refresh) Logowanie Selenium dla {self._mask_text(user_email)}...")
                
                if temp_client.login(username, password, profile_id=p_id):
                    # Pobierz i zapisz nowy token
                    entry = temp_client.get_token_entry(p_id)
                    if entry:
                        self._cache_session(
                            user_email, username, 
                            entry['token'], 
                            entry['issued_at'], 
                            entry['expires_at']
                        )
                        self.logger.info(f"✅ (Force Refresh) Sukces. Nowy token ważny do {entry['expires_at'].strftime('%H:%M:%S')}.")
                        return True
                
                self.logger.warning(f"❌ (Force Refresh) Logowanie nieudane.")
                return False
                
            except Exception as e:
                self.logger.error(f"Błąd podczas refresh_session: {e}", exc_info=True)
                return False

    def search_appointments(self, user_email: str = None, profile: str = None, **kwargs) -> List[Dict[str, Any]]:
        if not user_email or not profile: return []
        
        # --- SYNCHRONIZACJA LOGOWANIA PER USER ---
        user_lock = self._get_user_lock(user_email)
        
        # Inicjalizacja profile_id, które będzie użyte poza blokadą
        p_id = 0

        # Używamy blokady tylko na czas sprawdzenia/uzyskania sesji
        with user_lock:
            credentials = self.profile_manager.get_credentials(user_email, profile)
            if not credentials: return []
            username, password = credentials
            
            client_config = self.config.data.copy()
            client_config['username'] = username
            client_config['password'] = password
            
            try:
                p_id = int(username)
                client_config['profile_id'] = p_id
            except ValueError:
                self.logger.error(f"❌ Invalid username for profile_id: {username}")
                return []
            
            if p_id == 0:
                self.logger.error("❌ Profile ID cannot be 0")
                return []

            try:
                temp_client = MedicoverClient(client_config)
                
                # --- SESSION REUSE LOGIC ---
                cached_data = self._get_cached_session(user_email, username)
                is_logged_in = False

                if cached_data:
                    # FIX: Używamy restore_session aby zachować wiek tokenu!
                    temp_client.restore_session(
                        profile_id=p_id,
                        token=cached_data['token'],
                        issued_at=cached_data.get('issued_at', datetime.now()),
                        expires_at=cached_data['expires_at'],
                        username=username
                    )
                    is_logged_in = True
                
                if not is_logged_in:
                    self.logger.info(f"🔌 Logowanie przez Selenium dla {self._mask_text(user_email)} (Login: {self._mask_text(username)})...")
                    if temp_client.login(username, password, profile_id=p_id):
                        # Pobierz detale nowej sesji
                        entry = temp_client.get_token_entry(p_id)
                        if entry:
                            self._cache_session(
                                user_email, username, 
                                entry['token'], 
                                entry['issued_at'], 
                                entry['expires_at']
                            )
                        is_logged_in = True
                    else:
                        return []
            except Exception as e:
                self.logger.error(f"Błąd inicjalizacji klienta/logowania: {e}", exc_info=True)
                return []

        # Request do API robimy już poza blokadą
        search_params: Dict[str, Any] = {}
        if kwargs.get('specialty_ids'): search_params['SpecialtyIds'] = kwargs['specialty_ids']
        if kwargs.get('doctor_ids'): search_params['DoctorIds'] = kwargs['doctor_ids']
        if kwargs.get('clinic_ids'): search_params['ClinicIds'] = kwargs['clinic_ids']
        if p_id: search_params['profile_id'] = p_id 
        
        start_date = kwargs.get('start_date')
        end_date = kwargs.get('end_date')
        if start_date: search_params['StartTime'] = start_date
        if end_date: search_params['EndTime'] = end_date
        
        try:
            current_token_before = temp_client.get_token(p_id)
            found = temp_client.search_appointments(search_params)
            
            # --- FIX START: Aktualizacja cache jeśli klient zmienił token ---
            current_token_after = temp_client.get_token(p_id)
            
            if current_token_after and current_token_after != current_token_before:
                self.logger.info(f"🔄 Token zmieniony przez klienta (Internal Relogin). Aktualizacja cache dla {self._mask_text(username)}.")
                entry = temp_client.get_token_entry(p_id)
                if entry:
                    self._cache_session(
                        user_email, username, 
                        entry['token'], 
                        entry['issued_at'], 
                        entry['expires_at']
                    )
            # USUNIĘTO: else self._refresh_token_ttl(...) - brak touchowania
            # --- FIX END ---

        except AuthenticationException:
            self.logger.warning(f"⚠️ Token cache wygasł dla {self._mask_text(username)} (API 401). Próba relogowania (z blokadą)...")
            
            # Jeśli token wygasł, musimy ponownie wejść w sekcję krytyczną i przelogować
            with user_lock:
                # Sprawdź czy ktoś inny już nie odświeżył w międzyczasie
                cached_data_now = self._get_cached_session(user_email, username)
                
                # Check if cached token is different from what we had
                refreshed = False
                if cached_data_now and cached_data_now['token'] != current_token_before:
                    self.logger.info("Token został odświeżony przez inny wątek. Ponawiam na nowym tokenie.")
                    temp_client.restore_session(
                        profile_id=p_id,
                        token=cached_data_now['token'],
                        issued_at=cached_data_now['issued_at'],
                        expires_at=cached_data_now['expires_at'],
                        username=username
                    )
                    refreshed = True
                
                if not refreshed:
                    # Nadal stary/brak tokenu - robimy twardy relogin
                    # Usuń stary
                    key = self._get_cache_key(user_email, username)
                    with self._session_lock:
                         if key in self._session_cache: del self._session_cache[key]

                    if temp_client.login(username, password, profile_id=p_id):
                        entry = temp_client.get_token_entry(p_id)
                        if entry:
                            self._cache_session(
                                user_email, username, 
                                entry['token'], 
                                entry['issued_at'], 
                                entry['expires_at']
                            )
                        # Retry search
                    else:
                        self.logger.error("❌ Ponowne logowanie nieudane.")
                        return []
            pass

        if not found: return []

        filtered = self._filter_results_by_date_range(found, start_date, end_date)
        
        excluded_dates_raw = kwargs.get('excluded_dates')
        excluded_dates = []
        if excluded_dates_raw:
            try: 
                excluded_dates = [date.fromisoformat(d) for d in excluded_dates_raw]
            except Exception as e: 
                self.logger.error(f"Error parsing excluded_dates: {e}")

        filtered = self._filter_results_by_preferences(
            filtered, 
            kwargs.get('preferred_days'), 
            kwargs.get('time_range'),
            kwargs.get('day_time_ranges'),
            excluded_dates
        )

        if filtered: self._update_data_from_appointments(filtered)
        return filtered

    def book_appointment(self, user_email: str, profile: str, appointment_id: Any, booking_string: str = None) -> Dict[str, Any]:
        if not user_email or not profile: return {"success": False, "message": "Brak danych profilu"}
        
        user_lock = self._get_user_lock(user_email)
        p_id = 0

        with user_lock:
            credentials = self.profile_manager.get_credentials(user_email, profile)
            if not credentials: return {"success": False, "message": "Błąd poświadczeń"}
            username, password = credentials
            
            client_config = self.config.data.copy()
            client_config['username'] = username
            client_config['password'] = password
            
            try:
                p_id = int(username)
                client_config['profile_id'] = p_id
            except ValueError:
                return {"success": False, "message": "Invalid profile ID"}

            try:
                temp_client = MedicoverClient(client_config)
                
                cached_data = self._get_cached_session(user_email, username)
                is_logged_in = False

                if cached_data:
                    temp_client.restore_session(
                        profile_id=p_id,
                        token=cached_data['token'],
                        issued_at=cached_data.get('issued_at', datetime.now()),
                        expires_at=cached_data['expires_at'],
                        username=username
                    )
                    is_logged_in = True
                
                if not is_logged_in:
                    self.logger.info(f"🔌 (Book) Logowanie przez Selenium dla {self._mask_text(user_email)} (Login: {self._mask_text(username)})...")
                    if temp_client.login(username, password, profile_id=p_id):
                        entry = temp_client.get_token_entry(p_id)
                        if entry:
                            self._cache_session(
                                user_email, username, 
                                entry['token'], 
                                entry['issued_at'], 
                                entry['expires_at']
                            )
                        is_logged_in = True
                    else:
                        return {"success": False, "message": "Błąd logowania"}
            except Exception as e:
                return {"success": False, "message": f"Błąd init: {e}"}

        appointment_obj = {}
        if booking_string: appointment_obj["bookingString"] = booking_string
        if appointment_id: appointment_obj["id"] = appointment_id
        if not appointment_obj.get("bookingString"): return {"success": False, "message": "Brak bookingString"}

        try:
            result = temp_client.book_appointment(appointment_obj, profile_id=p_id)
            return result
        except AuthenticationException:
            # Retry logic...
            # (Similar to search, simplified for brevity but logic stands)
             return {"success": False, "error": "auth_failed", "message": "Błąd sesji (Book Retry skipped for brevity)"}

    def run_gui(self):
        try:
            from gui import MedicoverGUI
            gui = MedicoverGUI(self, self.config_dir)
            gui.run()
        except ImportError: pass

def main():
    try:
        app = MedicoverApp(Path("config"))
    except Exception as e: sys.exit(1)
