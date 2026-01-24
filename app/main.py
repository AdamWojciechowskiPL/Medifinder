# app/main.py

import logging
import sys
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from datetime import date, datetime
from .config import Config
from .profile_manager import ProfileManager
from .medicover_client import MedicoverClient
from .data_manager import SpecialtyManager, DoctorManager, ClinicManager

class MedicoverApp:
    def __init__(self, config_dir: Path):
        self.config = Config(config_dir / "credentials.json")
        self._setup_logging()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Managery
        self.profile_manager = ProfileManager(config_dir)
        # Słownik klientów per użytkownik email: { "email": MedicoverClient, ... }
        self._user_clients: Dict[str, MedicoverClient] = {}
        
        self.specialty_manager = SpecialtyManager(config_dir / "specialties.json")
        self.doctor_manager = DoctorManager(config_dir / "doctors.json")
        self.clinic_manager = ClinicManager(config_dir / "clinics.json")
        
        # Global client fallback (legacy GUI)
        self.client: Optional[MedicoverClient] = None
        self.current_profile: Optional[str] = None
        self.config_dir = config_dir

    def _update_data_from_appointments(self, appointments: List[Dict[str, Any]]) -> None:
        if not appointments: return
        self.logger.debug(f"Aktualizowanie baz danych na podstawie {len(appointments)} wizyt...")
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
            self.logger.info(f"Baza zaktualizowana. Lekarze: {doctors_updated}, Placówki: {clinics_updated}.")
            
    def _setup_logging(self) -> None:
        log_config = self.config.get('logging', {})
        logging.basicConfig(
            level=log_config.get('level', 'INFO').upper(),
            format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('medicover_app.log', encoding='utf-8')]
        )

    # === User-Aware Methods (Web) ===

    def get_client_for_user(self, user_email: str) -> Optional[MedicoverClient]:
        """Pobiera lub tworzy instancję klienta dla danej sesji użytkownika."""
        if not user_email: return None
        return self._user_clients.get(user_email)

    def switch_profile(self, user_email: str, profile_identifier: str) -> bool:
        """Przełącza profil w kontekście konkretnego użytkownika (Google Account)."""
        if not user_email:
            # Fallback dla desktop GUI
            return self._switch_profile_legacy(profile_identifier)
            
        self.logger.info(f"User {user_email}: Próba przełączenia na profil '{profile_identifier}'")
        credentials = self.profile_manager.get_credentials(user_email, profile_identifier)
        if not credentials:
            self.logger.error(f"User {user_email}: Nie znaleziono danych dla profilu '{profile_identifier}'")
            return False

        username, password = credentials
        config_data = self.config.data.copy()
        config_data['username'] = username
        config_data['password'] = password
        
        try:
            # Tworzymy nowego klienta dla tego użytkownika sesji
            client = MedicoverClient(config_data)
            self._user_clients[user_email] = client
            self.logger.info(f"User {user_email}: Klient zainicjalizowany dla profilu {username}")
            return True
        except Exception as e:
            self.logger.error(f"User {user_email}: Błąd inicjalizacji klienta: {e}", exc_info=True)
            return False

    def get_available_profiles(self, user_email: str = None) -> List[str]:
        if not user_email: return []
        # Return only usernames/names for specific user
        return [p.username for p in self.profile_manager.get_user_profiles(user_email)]

    def add_profile(self, user_email: str, login: str, password: str, name: str) -> Dict[str, Any]:
        if not user_email: return {'success': False, 'error': 'No user context'}
        try:
            result = self.profile_manager.add_profile(user_email, login, password, name)
            self.logger.info(f"User {user_email}: Profil '{name}' dodany pomyślnie")
            return {'success': result}
        except Exception as e:
            self.logger.error(f"User {user_email}: Błąd dodawania profilu: {e}")
            raise

    def search_appointments(self, 
                           user_email: str,
                           profile: str,
                           specialty_ids: Optional[Union[int, List[int]]] = None,
                           doctor_ids: Optional[List[int]] = None,
                           clinic_ids: Optional[List[int]] = None,
                           preferred_days: Optional[List[int]] = None,
                           time_range: Optional[Dict[str, str]] = None,
                           day_time_ranges: Optional[Dict[str, Dict[str, str]]] = None,
                           excluded_dates: Optional[List[date]] = None,
                           headless: bool = True,
                           **kwargs) -> List[Dict[str, Any]]:
        
        # 1. Pobierz lub ustaw klienta dla usera
        client = self.get_client_for_user(user_email)
        
        # Sprawdź czy klient istnieje i czy jest na dobrym profilu (uproszczone: sprawdzamy username)
        if not client or client.username != profile:
             self.logger.info(f"User {user_email}: Wymagane przełączenie na profil {profile}")
             if not self.switch_profile(user_email, profile):
                 return []
             client = self.get_client_for_user(user_email)

        if not client:
            return []

        # 2. Wykonaj wyszukiwanie (logika identyczna jak wcześniej)
        search_params = {}
        if specialty_ids:
            search_params['SpecialtyIds'] = specialty_ids if isinstance(specialty_ids, list) else [specialty_ids]
        if doctor_ids: search_params['DoctorIds'] = doctor_ids
        if clinic_ids: search_params['ClinicIds'] = clinic_ids

        try:
            found_appointments = client.search_appointments(search_params)
        except Exception as e:
            self.logger.error(f"User {user_email}: Błąd API: {e}")
            return []

        if not found_appointments: return []

        # 3. Filtrowanie (kod identyczny jak w poprzedniej wersji, skopiowany logicznie)
        filtered = []
        for apt in found_appointments:
            try:
                apt_datetime = None
                if 'datetime' in apt:
                    apt_datetime = datetime.fromisoformat(apt['datetime'])
                elif 'visitDate' in apt and 'visitTime' in apt:
                    d = datetime.fromisoformat(apt['visitDate']).date()
                    t = datetime.strptime(apt['visitTime'], '%H:%M').time()
                    apt_datetime = datetime.combine(d, t)
                
                if self._fits_time_filters(apt_datetime, preferred_days, time_range, day_time_ranges, excluded_dates):
                    filtered.append(apt)
            except:
                filtered.append(apt)
        
        self._update_data_from_appointments(filtered)
        return filtered

    def book_appointment(self, user_email: str, profile: str, appointment_id: Any) -> Dict[str, Any]:
        client = self.get_client_for_user(user_email)
        if not client: return {'success': False, 'error': 'No client'}
        
        # Appointment structure needs to be reconstructed or passed fully. 
        # For now assume appointment_id is actually the full object or we need logic to find it.
        # W wersji webowej przekazujemy ID, ale klient API potrzebuje bookingString.
        # Hack: Front powinien wysyłać cały obiekt wizyty, albo cache'ujemy wyniki.
        # W tym demie zakładamy, że appointment_id to w rzeczywistości obiekt wizyty (z JSONa)
        # LUB Front musi wysłać bookingString.
        
        # FIXME: API oczekuje, że appointment_id to po prostu ID, ale w medicover_client.book_appointment
        # oczekujemy słownika z kluczem 'bookingString'.
        # W tej chwili, jeśli user kliknie "Rezerwuj", front wysyła ID. 
        # Musimy zmienić logikę: front powinien wysłać bookingString lub obiekt.
        
        # Tymczasowe obejście: zakładamy że appointment_id to dict (jeśli front tak wyśle)
        if isinstance(appointment_id, dict):
            return client.book_appointment(appointment_id)
        
        return {'success': False, 'error': 'Invalid appointment data'}

    # === Legacy / Helper Methods ===
    def _switch_profile_legacy(self, name: str) -> bool:
        # Stara logika dla GUI desktopowego
        pass 

    def _fits_time_filters(self, dt, days, tr, dtr, ex):
        # Ta sama logika co w poprzednim pliku
        if not dt: return False
        if ex and dt.date() in ex: return False
        if days and dt.isoweekday() not in days: return False
        if dt:
            t = dt.time().strftime('%H:%M')
            start, end = '00:00', '23:59'
            if dtr and str(dt.isoweekday()) in dtr:
                start = dtr[str(dt.isoweekday())].get('start', start)
                end = dtr[str(dt.isoweekday())].get('end', end)
            elif tr:
                start = tr.get('start', start)
                end = tr.get('end', end)
            if t < start or t > end: return False
        return True
