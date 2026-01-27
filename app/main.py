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
        # ZMIANA: Kluczem jest user_email_profile, aby rozdzielić sesje dla różnych profili tego samego usera.
        # Key: "user@email.com_ProfileName" -> Value: {'token': str, 'expires_at': datetime, 'last_used': datetime}
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        self._session_lock = threading.Lock()
        
        # ZMIANA: Blokady per użytkownik, aby uniknąć równoczesnego logowania
        self._user_locks: Dict[str, threading.Lock] = {}
        self._user_locks_lock = threading.Lock() # Do ochrony słownika blokad
        
        # ZMIANA: Przywracamy dłuższy TTL (np. 14 minut, standard to ok. 15-20 min idle)
        self.TOKEN_TTL_MINUTES = 14
        
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

        self.logger.info(f"START Filtrowanie pref: wejście={len(appointments)}, Excluded={excluded_dates}, PrefDays={preferred_days}")

        for apt in appointments:
            dt = self._parse_appointment_date_dt(apt)
            if not dt:
                self.logger.info("Odrzucono wizytę: Brak daty (dt is None)")
                filtered.append(apt) # Fail-open
                continue

            self.logger.info(f"Przetwarzanie wizyty: {dt} (Dzień tyg: {dt.weekday()})")

            # 0. Sprawdź wykluczone daty (blacklist)
            if excluded_dates:
                apt_date = dt.date()
                if apt_date in excluded_dates:
                    self.logger.info(f"-> Odrzucono (Excluded Date): {apt_date}")
                    continue

            # 1. Sprawdź dzień tygodnia (0=Pon, 6=Nd)
            weekday = dt.weekday()
            
            # Jeśli user zaznaczył "dni tygodnia" w checkboxach, sprawdź to
            if preferred_days and weekday not in preferred_days:
                self.logger.info(f"-> Odrzucono (Weekday): {weekday} not in {preferred_days}")
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
                    
                    if t < s_time or t > e_time:
                        self.logger.info(f"-> Odrzucono (Specific Time): {t} outside {s_time}-{e_time}")
                        continue # Poza zakresem specyficznym dla dnia
                    
                    specific_range_found = True
                except Exception:
                    self.logger.warning(f"Błąd parsowania zakresu dla dnia {weekday}")

            # Jeśli nie znaleziono specyficznego zakresu, użyj globalnego (jeśli zdefiniowany)
            if not specific_range_found:
                if global_start_time and t < global_start_time:
                    self.logger.info(f"-> Odrzucono (Global Start): {t} < {global_start_time}")
                    continue
                if global_end_time and t > global_end_time:
                    self.logger.info(f"-> Odrzucono (Global End): {t} > {global_end_time}")
                    continue

            self.logger.info(f"-> ZAAKCEPTOWANO: {dt}")
            filtered.append(apt)

        self.logger.info(f"KONIEC Filtrowanie pref: wyjście={len(filtered)}")
        return filtered

    def _filter_results_by_date_range(self, appointments: List[Dict[str, Any]], start_date: Optional[str], end_date: Optional[str]) -> List[Dict[str, Any]]:
        if not appointments:
            return appointments

        self.logger.info(f"START Filtrowanie zakresu dat: wejście={len(appointments)}, Start={start_date}, End={end_date}")

        start = None
        end = None
        
        def parse_date_input(d_str: str) -> Optional[date]:
            if not d_str:
                return None
            try:
                # Try parsing as date YYYY-MM-DD
                return date.fromisoformat(d_str)
            except ValueError:
                try:
                    # Try parsing as datetime (e.g. ISO from JS with time)
                    # Handle Z suffix manually if needed
                    s = d_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(s).date()
                except Exception:
                    return None

        if start_date:
            start = parse_date_input(start_date)
            if not start:
                self.logger.warning(f"Nieprawidłowy start_date: {start_date}")

        if end_date:
            end = parse_date_input(end_date)
            if not end:
                self.logger.warning(f"Nieprawidłowy end_date: {end_date}")

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
                # self.logger.info(f"-> Odrzucono (Too Early): {d} < {start}")
                continue
            if end and d > end:
                # self.logger.info(f"-> Odrzucono (Too Late): {d} > {end}")
                continue
            filtered.append(apt)

        self.logger.info(f"KONIEC Filtrowanie zakresu dat: wyjście={len(filtered)}")
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
    
    def _get_cache_key(self, user_email: str, profile_name: str) -> str:
        return f"{user_email}_{profile_name}"

    def _get_cached_session(self, user_email: str, profile_name: str) -> Optional[str]:
        """
        Pobiera aktywny token z cache dla użytkownika i profilu.
        """
        key = self._get_cache_key(user_email, profile_name)
        with self._session_lock:
            if key in self._session_cache:
                data = self._session_cache[key]
                now = datetime.now()
                
                # Sprawdź czy token nie wygasł
                if now < data['expires_at']:
                    # TOKEN JEST JESZCZE WAŻNY - Przedłużamy TTL (sliding window)
                    self._session_cache[key]['expires_at'] = now + timedelta(minutes=self.TOKEN_TTL_MINUTES)
                    self._session_cache[key]['last_used'] = now
                    self.logger.info(f"♻️ Użycie tokenu z cache dla {key} (przedłużono do {self._session_cache[key]['expires_at'].strftime('%H:%M:%S')})")
                    return data['token']
                else:
                    # Token wygasł - usuń z cache
                    self.logger.info(f"⏰ Token cache dla {key} wygasł. Usuwam z cache.")
                    del self._session_cache[key]
        return None

    def _cache_session(self, user_email: str, profile_name: str, token: str):
        """Zapisuje token do cache dla użytkownika i profilu."""
        key = self._get_cache_key(user_email, profile_name)
        now = datetime.now()
        with self._session_lock:
            self._session_cache[key] = {
                'token': token,
                'expires_at': now + timedelta(minutes=self.TOKEN_TTL_MINUTES),
                'last_used': now
            }
            self.logger.info(f"💾 Token cache dla {key} zapisany. Wygasa: {self._session_cache[key]['expires_at'].strftime('%H:%M:%S')}")

    def _refresh_token_ttl(self, user_email: str, profile_name: str):
        """
        Przedłuża TTL tokenu po udanym użyciu API.
        """
        key = self._get_cache_key(user_email, profile_name)
        with self._session_lock:
            if key in self._session_cache:
                now = datetime.now()
                self._session_cache[key]['expires_at'] = now + timedelta(minutes=self.TOKEN_TTL_MINUTES)
                self._session_cache[key]['last_used'] = now

    def search_appointments(self, user_email: str = None, profile: str = None, **kwargs) -> List[Dict[str, Any]]:
        if not user_email or not profile: return []
        
        # --- SYNCHRONIZACJA LOGOWANIA PER USER ---
        # Zapobiega równoległym logowaniom, które unieważniają nawzajem tokeny
        user_lock = self._get_user_lock(user_email)
        
        # Używamy blokady tylko na czas sprawdzenia/uzyskania sesji, a nie całego requestu
        with user_lock:
            credentials = self.profile_manager.get_credentials(user_email, profile)
            if not credentials: return []
            username, password = credentials
            
            client_config = self.config.data.copy()
            client_config['username'] = username
            client_config['password'] = password
            
            try:
                temp_client = MedicoverClient(client_config)
                
                # --- SESSION REUSE LOGIC ---
                cached_token = self._get_cached_session(user_email, profile)
                is_logged_in = False

                if cached_token:
                    if temp_client.api.set_bearer_token(cached_token):
                        temp_client.current_token = cached_token
                        is_logged_in = True
                
                if not is_logged_in:
                    self.logger.info(f"🔌 Logowanie przez Selenium dla {user_email} (Profil: {profile})...")
                    if temp_client.login(username, password):
                        self._cache_session(user_email, profile, temp_client.current_token)
                        is_logged_in = True
                    else:
                        return []
            except Exception as e:
                self.logger.error(f"Błąd inicjalizacji klienta/logowania: {e}")
                return []

        # Request do API robimy już poza blokadą, ale na tokenie który jest (miejmy nadzieję) stabilny
        search_params: Dict[str, Any] = {}
        if kwargs.get('specialty_ids'): search_params['SpecialtyIds'] = kwargs['specialty_ids']
        if kwargs.get('doctor_ids'): search_params['DoctorIds'] = kwargs['doctor_ids']
        if kwargs.get('clinic_ids'): search_params['ClinicIds'] = kwargs['clinic_ids']
        start_date = kwargs.get('start_date')
        end_date = kwargs.get('end_date')
        if start_date: search_params['StartTime'] = start_date
        if end_date: search_params['EndTime'] = end_date
        
        try:
            found = temp_client.search_appointments(search_params)
            # Sukces - odświeżamy TTL
            self._refresh_token_ttl(user_email, profile)
        except AuthenticationException:
            self.logger.warning(f"⚠️ Token cache wygasł dla {user_email}_{profile} (API 401). Próba relogowania (z blokadą)...")
            
            # Jeśli token wygasł, musimy ponownie wejść w sekcję krytyczną i przelogować
            with user_lock:
                # Sprawdź czy ktoś inny już nie odświeżył w międzyczasie
                cached_token_now = self._get_cached_session(user_email, profile)
                if cached_token_now and cached_token_now != temp_client.current_token:
                    # Ktoś już odświeżył token! Użyjmy nowego.
                    self.logger.info("Token został odświeżony przez inny wątek. Ponawiam na nowym tokenie.")
                    if temp_client.api.set_bearer_token(cached_token_now):
                         found = temp_client.search_appointments(search_params)
                    else:
                         found = []
                else:
                    # Nadal stary/brak tokenu - robimy twardy relogin
                    # Usuń stary
                    key = self._get_cache_key(user_email, profile)
                    with self._session_lock:
                         if key in self._session_cache: del self._session_cache[key]

                    if temp_client.login(username, password):
                        self._cache_session(user_email, profile, temp_client.current_token)
                        found = temp_client.search_appointments(search_params)
                    else:
                        self.logger.error("❌ Ponowne logowanie nieudane.")
                        return []

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
        with user_lock:
            credentials = self.profile_manager.get_credentials(user_email, profile)
            if not credentials: return {"success": False, "message": "Błąd poświadczeń"}
            username, password = credentials
            
            client_config = self.config.data.copy()
            client_config['username'] = username
            client_config['password'] = password
            
            try:
                temp_client = MedicoverClient(client_config)
                
                # --- SESSION REUSE LOGIC ---
                cached_token = self._get_cached_session(user_email, profile)
                is_logged_in = False

                if cached_token:
                    if temp_client.api.set_bearer_token(cached_token):
                        temp_client.current_token = cached_token
                        is_logged_in = True
                
                if not is_logged_in:
                    self.logger.info(f"🔌 (Book) Logowanie przez Selenium dla {user_email} (Profil: {profile})...")
                    if temp_client.login(username, password):
                        self._cache_session(user_email, profile, temp_client.current_token)
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
            result = temp_client.book_appointment(appointment_obj)
            return result
        except AuthenticationException:
            # Retry logic z blokadą...
            with user_lock:
                 # Sprawdź ponownie cache
                 cached_token_now = self._get_cached_session(user_email, profile)
                 if cached_token_now and cached_token_now != temp_client.current_token:
                      temp_client.api.set_bearer_token(cached_token_now)
                      return temp_client.book_appointment(appointment_obj)

                 self.logger.warning(f"⚠️ (Book) Token cache wygasł dla {user_email}_{profile}. Ponawiam logowanie...")
                 if temp_client.login(username, password):
                    self._cache_session(user_email, profile, temp_client.current_token)
                    return temp_client.book_appointment(appointment_obj)
                 else:
                    return {"success": False, "message": "Błąd odświeżania sesji przy rezerwacji"}

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
