"""
Główny moduł aplikacji Medicover, dedykowany do uruchamiania
interfejsu graficznego (GUI).
"""

import logging
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import date, datetime, time

# Zredukowane, niezbędne importy
from .config import Config
from .profile_manager import ProfileManager
from .medicover_client import MedicoverClient
from .data_manager import SpecialtyManager, DoctorManager, ClinicManager

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
                    
                    if t < s_time or t > e_time:
                        continue # Poza zakresem specyficznym dla dnia
                    
                    specific_range_found = True
                except Exception:
                    self.logger.warning(f"Błąd parsowania zakresu dla dnia {weekday}")

            # Jeśli nie znaleziono specyficznego zakresu, użyj globalnego (jeśli zdefiniowany)
            if not specific_range_found:
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
        try:
            if start_date:
                start = date.fromisoformat(start_date)
        except Exception:
            self.logger.warning(f"Nieprawidłowy start_date: {start_date}")

        try:
            if end_date:
                end = date.fromisoformat(end_date)
        except Exception:
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
                continue
            if end and d > end:
                continue
            filtered.append(apt)

        return filtered
        
    def _update_data_from_appointments(self, appointments: List[Dict[str, Any]]) -> None:
        """
        Przetwarza listę wizyt i aktualizuje bazy danych lekarzy i placówek.
        """
        if not appointments:
            return

        doctors_updated = 0
        clinics_updated = 0

        for apt in appointments:
            doctor = apt.get('doctor')
            clinic = apt.get('clinic')
            specialty = apt.get('specialty')
            
            if doctor and specialty:
                if self.doctor_manager.add_or_update(doctor, specialty.get('id')):
                    doctors_updated += 1
            
            if clinic:
                if self.clinic_manager.add_or_update(clinic):
                    clinics_updated += 1
        
        if doctors_updated > 0 or clinics_updated > 0:
            self.logger.info(f"Aktualizacja baz danych zakończona. Nowi lekarze: {doctors_updated}, nowe placówki: {clinics_updated}.")
            
    def _setup_logging(self) -> None:
        """Konfiguruje system logowania na podstawie danych z pliku config."""
        log_config = self.config.get('logging', {})
        logging.basicConfig(
            level=log_config.get('level', 'INFO').upper(),
            format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('medicover_app.log', encoding='utf-8')]
        )

    def _initialize_default_profile_and_client(self) -> None:
        if self.profile_manager.profiles_path.exists():
             pass
        else:
            self.logger.warning("Nie znaleziono pliku profili.")

    def switch_profile(self, profile_name: str) -> bool:
        self.logger.warning("switch_profile called without user context - legacy method")
        return False

    def get_available_profiles(self, user_email: str) -> List[str]:
        return [p.username for p in self.profile_manager.get_user_profiles(user_email)]

    def get_current_profile(self) -> Optional[str]:
        return self.current_profile
    
    def add_profile(self, user_email: str, login: str, password: str, name: str, is_child_account: bool = False) -> bool:
        return self.profile_manager.add_profile(user_email, login, password, name, is_child_account)

    def search_appointments(self, user_email: str = None, profile: str = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Publiczna metoda do wyszukiwania wizyt.
        Tworzy tymczasowego klienta na podstawie przekazanego profilu.
        """
        if not user_email or not profile:
            self.logger.error("Brak kontekstu użytkownika lub profilu do wyszukiwania.")
            return []
            
        credentials = self.profile_manager.get_credentials(user_email, profile)
        if not credentials:
             self.logger.error(f"Nie znaleziono poświadczeń dla {profile}")
             return []
             
        username, password = credentials
        
        # Konfiguracja klienta
        client_config = self.config.data.copy()
        client_config['username'] = username
        client_config['password'] = password
        
        try:
            temp_client = MedicoverClient(client_config)
            if not temp_client.login(username, password):
                 self.logger.error("Logowanie nieudane")
                 return []

            # Przygotowanie parametrów wyszukiwania API
            search_params: Dict[str, Any] = {}
            if kwargs.get('specialty_ids'): search_params['SpecialtyIds'] = kwargs['specialty_ids']
            if kwargs.get('doctor_ids'): search_params['DoctorIds'] = kwargs['doctor_ids']
            if kwargs.get('clinic_ids'): search_params['ClinicIds'] = kwargs['clinic_ids']
            
            # Parametry dat
            start_date = kwargs.get('start_date')
            end_date = kwargs.get('end_date')
            if start_date:
                search_params['StartTime'] = start_date
            if end_date:
                search_params['EndTime'] = end_date
            
            # Wyszukiwanie w API
            found = temp_client.search_appointments(search_params)
            if not found:
                return []

            # --- FILTROWANIE WYNIKÓW ---
            # 1. Filtrowanie po zakresie dat (serwerowy fallback)
            filtered = self._filter_results_by_date_range(found, start_date, end_date)
            
            # 2. Filtrowanie po preferencjach (dni tygodnia, godziny, wykluczenia)
            preferred_days = kwargs.get('preferred_days')
            time_range = kwargs.get('time_range')
            day_time_ranges = kwargs.get('day_time_ranges')
            excluded_dates_raw = kwargs.get('excluded_dates')
            
            excluded_dates = []
            if excluded_dates_raw:
                try:
                    excluded_dates = [date.fromisoformat(d) for d in excluded_dates_raw]
                except Exception as e:
                    self.logger.warning(f"Błąd parsowania excluded_dates: {e}")

            filtered = self._filter_results_by_preferences(
                filtered, 
                preferred_days, 
                time_range,
                day_time_ranges,
                excluded_dates
            )

            if filtered:
                self._update_data_from_appointments(filtered)

            return filtered
            
        except Exception as e:
            self.logger.error(f"Błąd podczas wyszukiwania: {e}", exc_info=True)
            return []

    def book_appointment(self, user_email: str, profile: str, appointment_id: Any, booking_string: str = None) -> Dict[str, Any]:
        """
        Publiczna metoda do rezerwacji wizyty.
        """
        if not user_email or not profile:
             return {"success": False, "message": "Brak danych profilu"}
             
        credentials = self.profile_manager.get_credentials(user_email, profile)
        if not credentials:
             return {"success": False, "message": "Błąd poświadczeń"}
             
        username, password = credentials
        client_config = self.config.data.copy()
        client_config['username'] = username
        client_config['password'] = password
        
        try:
            temp_client = MedicoverClient(client_config)
            if not temp_client.login(username, password):
                 return {"success": False, "message": "Błąd logowania"}
            
            appointment_obj = {}
            if booking_string:
                appointment_obj["bookingString"] = booking_string
            
            if appointment_id:
                 appointment_obj["id"] = appointment_id

            if not appointment_obj.get("bookingString"):
                return {"success": False, "message": "Brak wymaganego pola 'bookingString' do rezerwacji."}

            return temp_client.book_appointment(appointment_obj)
            
        except Exception as e:
            self.logger.error(f"Błąd rezerwacji: {e}")
            return {"success": False, "message": str(e)}

    def run_gui(self):
        """Tworzy i uruchamia interfejs graficzny."""
        print("🚀 Uruchamianie interfejsu graficznego...")
        try:
            from gui import MedicoverGUI
            gui = MedicoverGUI(self, self.config_dir)
            gui.run()
        except ImportError:
            print("GUI module not available in this environment")

def main():
    """Główna funkcja aplikacji."""
    try:
        app = MedicoverApp(Path("config"))
        print("✅ Aplikacja zainicjalizowana")
    except Exception as e:
        print(f"❌ Błąd krytyczny: {e}")
        sys.exit(1)
