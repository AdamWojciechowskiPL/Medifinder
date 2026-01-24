# app/profile_manager.py

import json
import os
import logging
import base64
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from cryptography.fernet import Fernet
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class UserProfile:
    username: str
    password: str
    description: str = ""
    is_child_account: bool = False
    default: bool = False
    created: str = ""
    last_used: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserProfile':
        return cls(**data)


class ProfileManager:

    def __init__(self, config_dir: Path):
        self.logger = logging.getLogger(__name__)
        self.profiles_path = config_dir / "profiles.json"
        
        # Słownik przechowujący profile per email użytkownika Google
        # Struktura: { "email@gmail.com": [UserProfile, UserProfile], ... }
        self._user_profiles: Dict[str, List[UserProfile]] = {}
        
        # Klucz szyfrujący pobieramy ze zmiennych środowiskowych dla bezpieczeństwa
        self.key = self._load_key_from_env()
        self.cipher = Fernet(self.key)
        
        self.load_profiles()

    def _load_key_from_env(self) -> bytes:
        """
        Pobiera klucz szyfrujący ze zmiennej środowiskowej ENCRYPTION_KEY.
        Jeśli nie istnieje, generuje tymczasowy (dane przepadną po restarcie serwera!).
        """
        env_key = os.environ.get("ENCRYPTION_KEY")
        if env_key:
            try:
                return env_key.encode()
            except Exception as e:
                self.logger.critical(f"Klucz ENCRYPTION_KEY jest nieprawidłowy: {e}")
                raise ValueError("Invalid ENCRYPTION_KEY")
        
        self.logger.warning("⚠️ BRAK ENCRYPTION_KEY W ZMIENNYCH ŚRODOWISKOWYCH! Używam klucza tymczasowego. Po restarcie serwera nie odczytasz zapisanych haseł.")
        return Fernet.generate_key()

    def _encrypt_password(self, password: str) -> str:
        encrypted = self.cipher.encrypt(password.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')

    def _decrypt_password(self, encrypted_password: str) -> str:
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode('utf-8'))
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Błąd deszyfrowania hasła: {e}")
            raise ValueError("Password decryption failed")

    def load_profiles(self) -> bool:
        if not self.profiles_path.exists():
            self._user_profiles = {}
            return True

        try:
            with open(self.profiles_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Obsługa migracji ze starego formatu (lista) na nowy (słownik)
            if isinstance(data, list) or (isinstance(data, dict) and "profiles" in data):
                # Stary format - brak właściciela. Przypisujemy do 'legacy_migration' lub czyścimy
                self.logger.warning("Wykryto stary format pliku profili. Konwersja wymagana.")
                self._user_profiles = {} 
            else:
                # Nowy format: { "email": [profiles...] }
                self._user_profiles = {}
                for email, profiles_list in data.items():
                    if email == "metadata": continue
                    self._user_profiles[email] = [UserProfile.from_dict(p) for p in profiles_list]
            
            self.logger.info(f"Wczytano dane dla {len(self._user_profiles)} użytkowników.")
            return True
            
        except Exception as e:
            self.logger.error(f"Nie udało się wczytać profili: {e}")
            self._user_profiles = {}
            return False

    def save_profiles(self) -> bool:
        try:
            # Konwertujemy obiekty na dicty
            data_to_save = {}
            for email, profiles in self._user_profiles.items():
                data_to_save[email] = [p.to_dict() for p in profiles]
            
            data_to_save["metadata"] = { "last_updated": datetime.now().isoformat() }
            
            with open(self.profiles_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            
            # Próba ustawienia uprawnień (może nie działać na wszystkich systemach plików)
            try:
                os.chmod(self.profiles_path, 0o600)
            except:
                pass
                
            return True
        except Exception as e:
            self.logger.error(f"Nie udało się zapisać profili: {e}")
            return False

    # === Metody publiczne z kontekstem użytkownika (email) ===

    def get_user_profiles(self, user_email: str) -> List[UserProfile]:
        if not user_email: return []
        return self._user_profiles.get(user_email, []).copy()

    def get_profile(self, user_email: str, identifier: str) -> Optional[UserProfile]:
        """Szuka profilu po loginie lub nazwie w obrębie danego użytkownika."""
        profiles = self.get_user_profiles(user_email)
        return next((p for p in profiles if p.username == identifier or p.description == identifier), None)

    def add_profile(self, user_email: str, username: str, password: str, description: str = "", is_child_account: bool = False) -> bool:
        if not user_email: return False
        
        # Inicjalizacja listy dla nowego usera
        if user_email not in self._user_profiles:
            self._user_profiles[user_email] = []
        
        user_list = self._user_profiles[user_email]
        
        if any(p.username == username for p in user_list):
            self.logger.error(f"Profil '{username}' już istnieje dla użytkownika {user_email}.")
            return False
        
        encrypted_password = self._encrypt_password(password)
        
        # Pierwszy profil zawsze domyślny
        is_default = len(user_list) == 0
        
        profile = UserProfile(
            username=username,
            password=encrypted_password,
            description=description,
            is_child_account=is_child_account,
            default=is_default,
            created=datetime.now().isoformat()
        )
        
        self._user_profiles[user_email].append(profile)
        return self.save_profiles()

    def get_credentials(self, user_email: str, identifier: str) -> Optional[Tuple[str, str]]:
        profile = self.get_profile(user_email, identifier)
        if not profile:
            return None
        
        try:
            decrypted_pass = self._decrypt_password(profile.password)
            profile.last_used = datetime.now().isoformat()
            self.save_profiles()
            return (profile.username, decrypted_pass)
        except Exception:
            return None
