"""
Główny moduł aplikacji Medicover, dedykowany do uruchamiania
interfejsu graficznego (GUI).
"""

import logging
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import date, datetime
# Zredukowane, niezbędne importy
from config import Config
from profile_manager import ProfileManager
from medicover_client import MedicoverClient
from data_manager import SpecialtyManager, DoctorManager, ClinicManager

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
        
    def _update_data_from_appointments(self, appointments: List[Dict[str, Any]]) -> None:
        """
        Przetwarza listę wizyt i aktualizuje bazy danych lekarzy i placówek.
        """
        if not appointments:
            return

        self.logger.debug(f"Aktualizowanie baz danych na podstawie {len(appointments)} wizyt...")
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
        """
        Wczytuje domyślny profil, jeśli istnieje. Jeśli nie ma żadnych profili,
        aplikacja startuje bez aktywnego klienta.
        """
        if self.profile_manager.has_profiles():
            default_profile = self.profile_manager.get_default_profile()
            if default_profile:
                self.logger.info(f"Znaleziono domyślny profil: {default_profile.username}")
                self.switch_profile(default_profile.username)
            else:
                # Sytuacja rzadka, ale możliwa: profile istnieją, ale żaden nie jest domyślny
                self.logger.warning("Znaleziono profile, ale żaden nie jest ustawiony jako domyślny.")
        else:
            # KLUCZOWA ZMIANA: Nie robimy nic. Aplikacja wystartuje bez klienta.
            self.logger.warning("Nie znaleziono żadnych profili. Aplikacja oczekuje na stworzenie profilu przez użytkownika w GUI.")

    def switch_profile(self, profile_name: str) -> bool:
        """Przełącza aktywny profil i reinicjalizuje klienta Medicover."""
        self.logger.info(f"Próba przełączenia na profil: {profile_name}")
        credentials = self.profile_manager.get_credentials(profile_name)
        if not credentials:
            self.logger.error(f"Nie udało się znaleźć danych dla profilu '{profile_name}'.")
            return False

        self.current_profile = profile_name
        
        config_data_for_client = self.config.data.copy()
        config_data_for_client['username'], config_data_for_client['password'] = credentials
        
        try:
            self.client = MedicoverClient(config_data_for_client)
            self.logger.info(f"Pomyślnie przełączono i zainicjalizowano klienta dla profilu: {self.current_profile}")
            return True
        except Exception as e:
            self.logger.error(f"Nie udało się zainicjalizować klienta dla profilu '{profile_name}': {e}", exc_info=True)
            self.client = None
            return False

    def get_available_profiles(self) -> List[str]:
        """Zwraca listę nazw wszystkich dostępnych profili."""
        return [p.username for p in self.profile_manager.get_all_profiles()]

    def get_current_profile(self) -> Optional[str]:
        """Zwraca nazwę aktualnie aktywnego profilu."""
        return self.current_profile

    def add_profile(self, login: str, password: str, name: str) -> Dict[str, Any]:
        """Dodaje nowy profil do aplikacji."""
        try:
            result = self.profile_manager.add_profile(login, password, name)
            self.logger.info(f"Profil '{name}' dodany pomyślnie")
            return result
        except Exception as e:
            self.logger.error(f"Błąd dodawania profilu: {e}")
            raise

    def _fits_time_filters(self, 
                          appointment_datetime: datetime,
                          preferred_days: List[int],
                          time_range: Optional[Dict[str, str]],
                          day_time_ranges: Optional[Dict[str, Dict[str, str]]],
                          excluded_dates: Optional[List[date]]) -> bool:
        """
        Sprawdza, czy wizyta spełnia kryteria filtrowania czasowego.
        
        Args:
            appointment_datetime: Data i godzina wizyty
            preferred_days: Lista numerów dni tygodnia (1-7, Pn-Nd)
            time_range: Globalny zakres godzin {'start': 'HH:MM', 'end': 'HH:MM'}
            day_time_ranges: Zakresy godzin per dzień {'1': {'start': 'HH:MM', 'end': 'HH:MM'}, ...}
            excluded_dates: Lista wykluczonych dat
        
        Returns:
            True jeśli wizyta spełnia wszystkie kryteria, False w przeciwnym razie
        """
        if not appointment_datetime:
            self.logger.debug("appointment_datetime jest None")
            return False
        
        apt_date = appointment_datetime.date() if isinstance(appointment_datetime, datetime) else appointment_datetime
        apt_time = appointment_datetime.time() if isinstance(appointment_datetime, datetime) else None
        apt_weekday = apt_date.isoweekday()  # 1=Pn, 7=Nd
        
        # 1. Sprawdzenie wykluczonych dat
        if excluded_dates and apt_date in excluded_dates:
            self.logger.debug(f"Wizyta {apt_date} {apt_time} jest na liście wykluczonych dat")
            return False
        
        # 2. Sprawdzenie dnia tygodnia
        if preferred_days and apt_weekday not in preferred_days:
            self.logger.debug(f"Wizyta w dzień {apt_weekday} nie jest w preferred_days: {preferred_days}")
            return False
        
        # 3. Sprawdzenie zakresu godzin
        if apt_time:
            # Jeśli są zakresy per dzień, użyj ich; inaczej użyj globalnego zakresu
            if day_time_ranges and str(apt_weekday) in day_time_ranges:
                day_range = day_time_ranges[str(apt_weekday)]
                time_from = day_range.get('start', '00:00')
                time_to = day_range.get('end', '23:59')
            elif time_range:
                time_from = time_range.get('start', '00:00')
                time_to = time_range.get('end', '23:59')
            else:
                # Brak ograniczeń czasowych
                return True
            
            # Konwersja do porównywalnego formatu
            try:
                apt_time_str = apt_time.strftime('%H:%M') if hasattr(apt_time, 'strftime') else str(apt_time)[:5]
                if apt_time_str < time_from or apt_time_str > time_to:
                    self.logger.debug(f"Wizyta o {apt_time_str} nie mieści się w zakresie {time_from}-{time_to}")
                    return False
            except (ValueError, AttributeError) as e:
                self.logger.warning(f"Błąd porównania godzin: {e}")
                return False
        
        return True

    def search_appointments(self, 
                           profile: str,
                           specialty: str = '',
                           doctors: Optional[List[str]] = None,
                           clinics: Optional[List[str]] = None,
                           preferred_days: Optional[List[int]] = None,
                           time_range: Optional[Dict[str, str]] = None,
                           day_time_ranges: Optional[Dict[str, Dict[str, str]]] = None,
                           excluded_dates: Optional[List[date]] = None,
                           headless: bool = False) -> List[Dict[str, Any]]:
        """
        Wyszukuje wizyty ze wsparciem dla rozszerzonych filtrów czasowych.
        
        Args:
            profile: Nazwa profilu
            specialty: Specjalizacja
            doctors: Lista lekarzy
            clinics: Lista placówek
            preferred_days: Lista preferowanych dni tygodnia (1-7)
            time_range: Globalny zakres godzin {'start': 'HH:MM', 'end': 'HH:MM'}
            day_time_ranges: Zakresy godzin per dzień {'1': {'start': '08:00', 'end': '12:00'}, ...}
            excluded_dates: Lista wykluczonych dat
            headless: Tryb headless dla przeglądarki
        
        Returns:
            Lista wyszukanych wizyt
        """
        # Jeśli trzeba przełączyć profil
        if profile != self.current_profile:
            if not self.switch_profile(profile):
                self.logger.error(f"Nie udało się przełączyć na profil '{profile}'")
                return []
        
        if not self.client:
            self.logger.error("Wyszukiwanie niemożliwe: klient nie jest zainicjalizowany.")
            return []
        
        # Logowanie parametrów
        self.logger.info(f"Wyszukiwanie wizyt - specialty: {specialty}")
        self.logger.info(f"  preferred_days: {preferred_days}")
        self.logger.info(f"  time_range: {time_range}")
        self.logger.info(f"  day_time_ranges: {day_time_ranges}")
        self.logger.info(f"  excluded_dates: {excluded_dates}")
        
        # Przygotowanie parametrów dla API
        search_params = {
            'specialty': specialty,
            'doctors': doctors or [],
            'clinics': clinics or []
        }
        
        # Wyszukaj wizyty z API
        try:
            found_appointments = self.client.search_appointments(search_params)
        except Exception as e:
            self.logger.error(f"Błąd wyszukiwania z API: {e}")
            return []
        
        if not found_appointments:
            self.logger.info("API zwróciło pustą listę wizyt")
            return []
        
        self.logger.info(f"API zwróciło {len(found_appointments)} wizyt, stosowanie filtrów...")
        
        # Filtrowanie wyników na podstawie kryteriów czasowych
        filtered_appointments = []
        for apt in found_appointments:
            try:
                # Próbuj znaleźć datetime w wizycie
                apt_datetime = None
                if 'datetime' in apt:
                    apt_dt_str = apt['datetime']
                    apt_datetime = datetime.fromisoformat(apt_dt_str) if isinstance(apt_dt_str, str) else apt_dt_str
                elif 'visitDate' in apt and 'visitTime' in apt:
                    try:
                        date_part = datetime.fromisoformat(apt['visitDate']).date()
                        time_part = datetime.strptime(apt['visitTime'], '%H:%M').time()
                        apt_datetime = datetime.combine(date_part, time_part)
                    except (ValueError, AttributeError):
                        pass
                
                # Jeśli uda się zebrać datetime, sprawdzić filtry
                if apt_datetime:
                    if self._fits_time_filters(apt_datetime, 
                                              preferred_days or [],
                                              time_range,
                                              day_time_ranges,
                                              excluded_dates or []):
                        filtered_appointments.append(apt)
                    else:
                        self.logger.debug(f"Wizyta {apt_datetime} odfiltrowana")
                else:
                    # Jeśli nie ma datetime, dodaj wizytę (nie możemy filtrować)
                    self.logger.debug(f"Nie znaleziono datetime w wizycie: {apt}")
                    filtered_appointments.append(apt)
            except Exception as e:
                self.logger.warning(f"Błąd przetwarzania wizyty: {e}, dodaję do wyników")
                filtered_appointments.append(apt)
        
        self.logger.info(f"Po filtrowaniu: {len(filtered_appointments)} wizyt")
        
        # Aktualizacja baz danych
        if filtered_appointments:
            self._update_data_from_appointments(filtered_appointments)
            
        return filtered_appointments

    def auto_book_appointment(self,
                             profile: str,
                             specialty: str,
                             doctors: Optional[List[str]] = None,
                             clinics: Optional[List[str]] = None,
                             preferred_days: Optional[List[int]] = None,
                             time_range: Optional[Dict[str, str]] = None,
                             day_time_ranges: Optional[Dict[str, Dict[str, str]]] = None,
                             excluded_dates: Optional[List[date]] = None,
                             auto_book: bool = True,
                             headless: bool = False) -> Dict[str, Any]:
        """
        Wyszukuje i automatycznie rezerwuje pierwszą wolną wizytę spełniającą kryteria.
        
        Args:
            Takie same jak search_appointments + auto_book
        
        Returns:
            Słownik ze statusem rezerwacji
        """
        self.logger.info("🤖 Uruchamianie automatycznej rezerwacji...")
        
        # Wyszukaj wizyty
        appointments = self.search_appointments(
            profile=profile,
            specialty=specialty,
            doctors=doctors,
            clinics=clinics,
            preferred_days=preferred_days,
            time_range=time_range,
            day_time_ranges=day_time_ranges,
            excluded_dates=excluded_dates,
            headless=headless
        )
        
        if not appointments:
            self.logger.warning("❌ Nie znaleziono wolnych wizyt spełniających kryteria")
            return {
                'success': False,
                'message': 'Nie znaleziono wolnych wizyt',
                'appointments_found': 0
            }
        
        self.logger.info(f"✅ Znaleziono {len(appointments)} wizyt, rezerwuję pierwszą...")
        
        # Rezerwuj pierwszą wizytę
        first_appointment = appointments[0]
        try:
            result = self.book_appointment(profile, first_appointment)
            if result.get('success'):
                self.logger.info(f"✅ Wizyta zarezerwowana: {first_appointment}")
                return {
                    'success': True,
                    'message': 'Wizyta zarezerwowana',
                    'appointment': first_appointment,
                    'total_found': len(appointments)
                }
            else:
                self.logger.error(f"❌ Rezerwacja nie powiodła się: {result}")
                return {
                    'success': False,
                    'message': result.get('message', 'Rezerwacja nie powiodła się'),
                    'appointments_found': len(appointments)
                }
        except Exception as e:
            self.logger.error(f"❌ Błąd rezerwacji: {e}")
            return {
                'success': False,
                'message': f'Błąd: {e}',
                'appointments_found': len(appointments)
            }

    def book_appointment(self, profile: str, appointment: Dict[str, Any]) -> Dict[str, Any]:
        """Rezerwuje konkretną wizytę."""
        if profile != self.current_profile:
            if not self.switch_profile(profile):
                return {'success': False, 'error': 'profile_switch_failed'}
        
        if not self.client:
            self.logger.error("Rezerwacja niemożliwa: klient nie jest zainicjalizowany.")
            return {"success": False, "error": "client_not_initialized", "message": "Klient nie jest gotowy."}
        
        try:
            result = self.client.book_appointment(appointment)
            return result
        except Exception as e:
            self.logger.error(f"Błąd rezerwacji: {e}")
            return {"success": False, "error": "booking_failed", "message": str(e)}
    
    def run_gui(self):
        """Tworzy i uruchamia interfejs graficzny."""
        print("🚀 Uruchamianie interfejsu graficznego...")
        # Przekazujemy 'self' (czyli całą instancję app) oraz ścieżkę do konfiguracji
        from gui import MedicoverGUI
        gui = MedicoverGUI(self, self.config_dir)
        gui.run()

def main():
    """Główna funkcja aplikacji, która inicjalizuje i uruchamia GUI."""
    try:
        app = MedicoverApp()

        from gui import MedicoverGUI
        print("🚀 Uruchamianie interfejsu graficznego...")
        gui = MedicoverGUI(app)
        gui.run()

    except KeyboardInterrupt:
        print("\n🛑 Działanie przerwane przez użytkownika.")
    except Exception as e:
        try:
            logging.getLogger(__name__).error(f"Wystąpił błąd krytyczny: {e}", exc_info=True)
        except Exception:
            pass
        print(f"❌ Błąd krytyczny: {e}")
        sys.exit(1)
