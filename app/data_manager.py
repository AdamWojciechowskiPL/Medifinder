"""
Zarządzanie dynamicznymi i statycznymi bazami danych aplikacji,
przechowywanymi w plikach JSON. Zapewnia bezpieczny odczyt,
zapis i aktualizację danych dla specjalności, lekarzy i placówek.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional

# Inicjalizacja loggera dla tego modułu
logger = logging.getLogger(__name__)

class BaseDataManager:
    """
    Klasa bazowa do zarządzania plikiem danych JSON.
    Obsługuje bezpieczne ładowanie, zapisywanie i operacje na plikach.
    """
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.data: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._load_data()

    def _load_data(self) -> None:
        """
        Wczytuje dane z pliku JSON. Jeśli plik nie istnieje, tworzy go.
        """
        with self._lock:
            try:
                if self.file_path.exists():
                    with self.file_path.open('r', encoding='utf-8') as f:
                        self.data = json.load(f)
                else:
                    logger.warning(f"Plik danych '{self.file_path}' nie istnieje. Tworzenie nowego.")
                    self.data = {}
                    self._save_data_unlocked() # Zapisz pusty plik
            except json.JSONDecodeError:
                logger.error(f"Błąd parsowania pliku JSON: {self.file_path}. Używanie pustego zbioru danych.")
                self.data = {}
            except Exception as e:
                logger.error(f"Nie udało się wczytać danych z '{self.file_path}': {e}")
                self.data = {}

    def _save_data_unlocked(self) -> None:
        """
        Zapisuje dane do pliku JSON bez zakładania nowej blokady.
        Musi być wywoływana z metody, która już posiada blokadę.
        """
        try:
            # Upewnij się, że katalog nadrzędny istnieje
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open('w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Nie udało się zapisać danych do pliku '{self.file_path}': {e}")
            
    def _save_data(self) -> None:
        """Zapisuje bieżący stan danych do pliku JSON w sposób bezpieczny wątkowo."""
        with self._lock:
            self._save_data_unlocked()

    def get_all_names(self, is_child_account: bool = False) -> List[str]:
        """
        Zwraca posortowaną listę nazw specjalności, przefiltrowaną
        w zależności od tego, czy konto jest dla dziecka, czy dla dorosłego.

        Args:
            is_child_account: Flaga wskazująca, czy filtrować dla konta dziecka.

        Returns:
            Przefiltrowana i posortowana lista nazw specjalności.
        """
        with self._lock:
            filtered_specialties: List[str] = []
            for name, details in self.data.items():
                if is_child_account:
                    # Dla konta dziecka, POKAŻ specjalności, które NIE SĄ
                    # oznaczone jako "tylko dla dorosłych".
                    if not details.get("for_adult_account_only", False):
                        filtered_specialties.append(name)
                else:
                    # Dla konta dorosłego, POKAŻ specjalności, które NIE SĄ
                    # oznaczone jako "tylko dla dziecka".
                    if not details.get("for_child_account_only", False):
                        filtered_specialties.append(name)
            
            return sorted(filtered_specialties)

class SpecialtyManager(BaseDataManager):
    """
    Zarządza statyczną bazą specjalności (specialties.json).
    Plik ten powinien być edytowany ręcznie.
    """
    def __init__(self, file_path: str = "specialties.json"):
        super().__init__(file_path)
        if not self.data:
            logger.warning(f"Plik specjalności '{self.file_path}' jest pusty lub nie istnieje. "
                           f"Aplikacja nie będzie mogła wyszukiwać po specjalnościach. "
                           f"Proszę uzupełnić ten plik.")

    def get_ids_by_name(self, name: str) -> Optional[List[int]]:
        """
        Zwraca listę ID dla podanej nazwy specjalności.

        Args:
            name: Nazwa specjalności.

        Returns:
            Lista identyfikatorów lub None, jeśli nazwa nie została znaleziona.
        """
        with self._lock:
            specialty_data = self.data.get(name)
            return specialty_data.get('ids') if specialty_data else None

class DoctorManager(BaseDataManager):
    """
    Zarządza dynamicznie rozwijaną bazą lekarzy (doctors.json).
    """
    def __init__(self, file_path: str = "doctors.json"):
        super().__init__(file_path)

    def add_or_update(self, doctor_data: Dict[str, Any], specialty_id: int) -> bool:
        """
        Dodaje nowego lekarza lub aktualizuje istniejącego o nowy ID specjalności.

        Args:
            doctor_data: Słownik z danymi lekarza (oczekiwane klucze 'id' i 'name').
            specialty_id: ID specjalności powiązanej z daną wizytą.

        Returns:
            True, jeśli dane zostały zmienione, w przeciwnym razie False.
        """
        doctor_id = doctor_data.get('id')
        doctor_name = doctor_data.get('name')

        if not all([doctor_id, doctor_name, specialty_id]):
            logger.debug("Brak kompletnych danych lekarza lub specjalności do zapisu.")
            return False

        changed = False
        with self._lock:
            entry = self.data.get(doctor_name)
            if not entry:
                # Dodaj nowego lekarza
                self.data[doctor_name] = {
                    'id': doctor_id,
                    'specialty_ids': [specialty_id]
                }
                logger.info(f"Dodano nowego lekarza do bazy: {doctor_name}")
                changed = True
            else:
                # Zaktualizuj istniejącego, jeśli trzeba
                if specialty_id not in entry.get('specialty_ids', []):
                    entry['specialty_ids'].append(specialty_id)
                    logger.info(f"Zaktualizowano specjalności dla lekarza: {doctor_name}")
                    changed = True
            
            if changed:
                self._save_data_unlocked()
        
        return changed

    def get_id_by_name(self, name: str) -> Optional[str]:
        """Zwraca ID dla podanego lekarza."""
        with self._lock:
            return self.data.get(name, {}).get('id')
    def get_all_doctors_data(self) -> Dict[str, Any]:
        """
        Zwraca kopię słownika ze wszystkimi danymi lekarzy.
        Kluczem jest nazwa lekarza.
        """
        with self._lock:
            return self.data.copy()
            
    def get_ids_by_names(self, names: list[str]) -> list[str]:
        """Zwraca listę ID dla podanej listy nazw lekarzy."""
        with self._lock:
            ids = [self.data.get(name, {}).get('id') for name in names]
            return [doc_id for doc_id in ids if doc_id] # Zwróć tylko te, które nie są None
class ClinicManager(BaseDataManager):
    """
    Zarządza dynamicznie rozwijaną bazą placówek (clinics.json).
    """
    def __init__(self, file_path: str = "clinics.json"):
        super().__init__(file_path)

    def add_or_update(self, clinic_data: Dict[str, Any]) -> bool:
        """
        Dodaje nową placówkę, jeśli jeszcze nie istnieje w bazie.

        Args:
            clinic_data: Słownik z danymi placówki (oczekiwane klucze 'id' i 'name').

        Returns:
            True, jeśli dane zostały zmienione, w przeciwnym razie False.
        """
        clinic_id = clinic_data.get('id')
        clinic_name = clinic_data.get('name')

        if not all([clinic_id, clinic_name]):
            logger.debug("Brak kompletnych danych placówki do zapisu.")
            return False
            
        changed = False
        with self._lock:
            if clinic_name not in self.data:
                self.data[clinic_name] = {'id': clinic_id}
                logger.info(f"Dodano nową placówkę do bazy: {clinic_name}")
                changed = True
        
            if changed:
                self._save_data_unlocked()

        return changed

    def get_id_by_name(self, name: str) -> Optional[str]:
        """Zwraca ID dla podanej placówki."""
        with self._lock:
            return self.data.get(name, {}).get('id')
            
    def get_ids_by_names(self, names: list[str]) -> list[str]:
        """Zwraca listę ID dla podanej listy nazw placówek."""
        with self._lock:
            ids = [self.data.get(name, {}).get('id') for name in names]
            return [clinic_id for clinic_id in ids if clinic_id] # Zwróć tylko te, które nie są None
