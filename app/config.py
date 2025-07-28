"""
Zrefaktoryzowana, uproszczona klasa do zarządzania plikiem konfiguracyjnym.
Skupia się wyłącznie na wczytywaniu, zapisywaniu i dostarczaniu wartości
konfiguracyjnych, delegując zarządzanie profilami do ProfileManagera.
"""
import json
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class Config:
    """
    Zarządza konfiguracją aplikacji z pliku JSON.
    Zapewnia domyślne wartości i bezpieczny zapis/odczyt.
    """
    
    # Prywatna zmienna klasowa z domyślną strukturą i wartościami.
    _DEFAULT_CONFIG = {
        # Dane logowania (używane tylko jeśli nie ma aktywnego profilu)
        "username": "",
        "password": "",
        
        # Parametry wyszukiwania wizyt
        "search_params": {
            "region_ids": [204],
            "page": 1,
            "page_size": 5000,
            "slot_search_type": "Standard",
            "is_overbooking_search_disabled": False
        },
        
        # Ustawienia aplikacji
        "check_interval_minutes": 5,
        "headless": True,  # Domyślnie tryb widoczny dla większej niezawodności
        
        # Konfiguracja logowania
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        }
    }

    def __init__(self, config_path: Path):
        self.config_file = config_path
        self.data: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """
        Wczytuje konfigurację z pliku JSON. Jeśli plik nie istnieje,
        tworzy go z domyślnymi wartościami.
        """
        try:
            if self.config_file.exists():
                with self.config_file.open('r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                # Łączenie wczytanej konfiguracji z domyślną, aby uzupełnić brakujące klucze
                self.data = self._deep_merge(self._DEFAULT_CONFIG.copy(), loaded_config)
                logger.info(f"Konfiguracja wczytana pomyślnie z {self.config_file}")
            else:
                logger.warning(f"Plik konfiguracyjny {self.config_file} nie istnieje. Tworzenie domyślnej konfiguracji.")
                self.data = self._DEFAULT_CONFIG.copy()
                self.save()
        except json.JSONDecodeError:
            logger.error(f"Błąd parsowania pliku JSON: {self.config_file}. Używanie konfiguracji domyślnej.")
            self.data = self._DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"Nie udało się wczytać konfiguracji: {e}. Używanie konfiguracji domyślnej.")
            self.data = self._DEFAULT_CONFIG.copy()

    def save(self) -> None:
        """Zapisuje aktualną konfigurację do pliku JSON."""
        try:
            with self.config_file.open('w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            logger.debug(f"Konfiguracja zapisana do pliku {self.config_file}")
        except Exception as e:
            logger.error(f"Nie udało się zapisać konfiguracji do pliku {self.config_file}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Zwraca wartość dla danego klucza z konfiguracji.

        Args:
            key: Klucz do wyszukania.
            default: Wartość do zwrócenia, jeśli klucz nie zostanie znaleziony.

        Returns:
            Wartość konfiguracyjna lub wartość domyślna.
        """
        return self.data.get(key, default)

    def get_summary(self) -> Dict[str, Any]:
        """
        Zwraca podsumowanie konfiguracji z ukrytymi danymi wrażliwymi.
        """
        # Tworzymy głęboką kopię, aby nie modyfikować oryginalnych danych
        summary = json.loads(json.dumps(self.data))
        
        # Ukryj hasła i inne dane wrażliwe
        if 'password' in summary:
            summary['password'] = '***'
        if summary.get('notification', {}).get('email', {}).get('sender_password'):
            summary['notification']['email']['sender_password'] = '***'
        if summary.get('notification', {}).get('webhook', {}).get('url'):
            url = summary['notification']['webhook']['url']
            if len(url) > 15:
                summary['notification']['webhook']['url'] = url[:15] + '...'
                
        return summary

    def _deep_merge(self, default: Dict, loaded: Dict) -> Dict:
        """
        Rekursywnie łączy dwa słowniki, nadpisując wartości domyślne
        tymi wczytanymi z pliku.
        """
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result