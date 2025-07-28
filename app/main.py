"""
Główny moduł aplikacji Medicover, dedykowany do uruchamiania
interfejsu graficznego (GUI).
"""

import logging
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path
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

    def search_appointments(self, search_params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Publiczna metoda do wyszukiwania wizyt. Deleguje zadanie do klienta."""
        if not self.client:
            self.logger.error("Wyszukiwanie niemożliwe: klient nie jest zainicjalizowany.")
            return []
        
        found_appointments = self.client.search_appointments(search_params)
        
        if found_appointments:
            self._update_data_from_appointments(found_appointments)
            
        return found_appointments

    def book_appointment(self, appointment: Dict[str, Any]) -> Dict[str, Any]:
        """Publiczna metoda do rezerwacji wizyty. Deleguje zadanie do klienta."""
        if not self.client:
            self.logger.error("Rezerwacja niemożliwa: klient nie jest zainicjalizowany.")
            return {"success": False, "error": "client_not_initialized", "message": "Klient nie jest gotowy."}
        return self.client.book_appointment(appointment)
    def run_gui(self):
        """Tworzy i uruchamia interfejs graficzny."""
        print("🚀 Uruchamianie interfejsu graficznego...")
        # Przekazujemy 'self' (czyli całą instancję app) oraz ścieżkę do konfiguracji
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
