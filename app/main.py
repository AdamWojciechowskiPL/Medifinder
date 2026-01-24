"""
Główny moduł aplikacji Medicover, dedykowany do uruchamiania
interfejsu graficznego (GUI).
"""

import logging
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path
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
        if self.profile_manager.profiles_path.exists(): # Sprawdzenie czy plik istnieje, bo user_profiles moze byc puste
             # Tutaj logika może wymagać dostosowania do nowej struktury ProfileManager
             # która używa user_email jako klucza. 
             # W wersji webowej, kontekst użytkownika jest przekazywany dynamicznie,
             # więc inicjalizacja "domyślnego" klienta może nie być potrzebna lub możliwa bez emaila.
             pass
        else:
            self.logger.warning("Nie znaleziono pliku profili.")

    def switch_profile(self, profile_name: str) -> bool:
        """
        Przełącza aktywny profil i reinicjalizuje klienta Medicover.
        UWAGA: W wersji webowej ta metoda może być mniej używana, bo profil wybieramy per request.
        """
        # Ta metoda wymagałaby user_email, którego tu nie mamy w kontekście globalnym
        self.logger.warning("switch_profile called without user context - legacy method")
        return False

    def get_available_profiles(self, user_email: str) -> List[str]:
        """Zwraca listę nazw wszystkich dostępnych profili dla danego użytkownika."""
        return [p.username for p in self.profile_manager.get_user_profiles(user_email)]

    def get_current_profile(self) -> Optional[str]:
        """Zwraca nazwę aktualnie aktywnego profilu."""
        return self.current_profile
    
    def add_profile(self, user_email: str, login: str, password: str, name: str, is_child_account: bool = False) -> bool:
        """Dodaje nowy profil użytkownika."""
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
            # Logowanie
            if not temp_client.login(username, password):
                 self.logger.error("Logowanie nieudane")
                 return []
                 
            # Przygotowanie parametrów wyszukiwania (mapowanie kwargs na format API)
            search_params = {}
            if kwargs.get('specialty_ids'): search_params['SpecialtyIds'] = kwargs['specialty_ids']
            if kwargs.get('doctor_ids'): search_params['DoctorIds'] = kwargs['doctor_ids']
            if kwargs.get('clinic_ids'): search_params['ClinicIds'] = kwargs['clinic_ids']
            
            # Obsługa dat i godzin... (uproszczona)
            # Tutaj normalnie byłaby logika konwersji time_range itp.
            # Zakładamy, że MedicoverClient radzi sobie z podstawowymi parametrami
            
            # Wywołanie search_appointments w kliencie
            found = temp_client.search_appointments(search_params)
            
            if found:
                self._update_data_from_appointments(found)
                return found
            return []
            
        except Exception as e:
            self.logger.error(f"Błąd podczas wyszukiwania: {e}", exc_info=True)
            return []

    def book_appointment(self, user_email: str, profile: str, appointment_id: int) -> Dict[str, Any]:
        """Publiczna metoda do rezerwacji wizyty."""
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
            
            # Rezerwacja wymaga obiektu appointment lub chociaż ID. 
            # MedicoverClient.book_appointment oczekuje całego słownika wizyty,
            # więc tutaj musielibyśmy najpierw pobrać szczegóły wizyty lub skonstruować obiekt.
            # Zakładam, że client ma metodę book_appointment_by_id lub radzi sobie z minimalnym obiektem.
            fake_appointment_obj = {"id": appointment_id}
            return temp_client.book_appointment(fake_appointment_obj)
            
        except Exception as e:
            self.logger.error(f"Błąd rezerwacji: {e}")
            return {"success": False, "message": str(e)}

    def run_gui(self):
        """Tworzy i uruchamia interfejs graficzny."""
        print("🚀 Uruchamianie interfejsu graficznego...")
        # Przekazujemy 'self' (czyli całą instancję app) oraz ścieżkę do konfiguracji
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
