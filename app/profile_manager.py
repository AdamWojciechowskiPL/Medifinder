# app/profile_manager.py

import json
import os
import logging
import base64
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from cryptography.fernet import Fernet
from dataclasses import dataclass, asdict
from pathlib import Path

# Dataclass UserProfile pozostaje bez zmian
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
        """
        Inicjalizuje menedżera profili. Wersja ujednolicona i poprawiona.
        """
        # POPRAWKA: Inicjalizacja loggera
        self.logger = logging.getLogger(__name__)

        # POPRAWKA: Ujednolicenie ścieżek
        self.profiles_path = config_dir / "profiles.json"
        self.key_path = config_dir / "profile_key.key"
        
        # POPRAWKA: Ujednolicenie nazwy listy profili
        self._profiles: List[UserProfile] = []
        
        # POPRAWKA: Użycie poprawnej, ujednoliconej metody do wczytywania klucza
        self.key = self._generate_or_load_key()
        
        # POPRAWKA: Ujednolicenie nazwy instancji szyfratora
        self.cipher = Fernet(self.key)
        
        # POPRAWKA: Wywołanie istniejącej, poprawnej metody wczytywania profili
        self.load_profiles()

    def _generate_or_load_key(self) -> bytes:
        """
        Wczytuje klucz szyfrujący z pliku lub tworzy nowy, jeśli nie istnieje.
        Wersja poprawiona: używa poprawnej ścieżki `self.key_path`.
        """
        try:
            # POPRAWKA: Użycie `self.key_path` zamiast hardkodowanej ścieżki
            key = self.key_path.read_bytes()
            # Prosta walidacja, czy klucz jest poprawny dla Fernet
            Fernet(key)
            return key
        except FileNotFoundError:
            self.logger.info(f"Nie znaleziono klucza, tworzenie nowego w: {self.key_path}")
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            os.chmod(self.key_path, 0o600)
            return key
        except Exception as e:
            self.logger.error(f"Klucz w {self.key_path} jest uszkodzony lub nieprawidłowy: {e}. Tworzenie nowego.")
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            os.chmod(self.key_path, 0o600)
            return key

    def _encrypt_password(self, password: str) -> str:
        """Szyfruje hasło."""
        # POPRAWKA: Użycie `self.cipher`
        encrypted = self.cipher.encrypt(password.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')

    def _decrypt_password(self, encrypted_password: str) -> str:
        """Deszyfruje hasło."""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode('utf-8'))
            # POPRAWKA: Użycie `self.cipher`
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Błąd deszyfrowania hasła: {e}")
            raise ValueError("Password decryption failed")

    def load_profiles(self) -> bool:
        """Wczytuje profile z pliku JSON."""
        # POPRAWKA: Użycie `self.profiles_path`
        if not self.profiles_path.exists():
            self.logger.info(f"Plik profili {self.profiles_path} nie istnieje, start z pustą listą.")
            self._profiles = []
            return True

        try:
            # POPRAWKA: Użycie `self.profiles_path`
            with open(self.profiles_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            profiles_data = data if isinstance(data, list) else data.get('profiles', [])
            
            self._profiles = [UserProfile.from_dict(p_data) for p_data in profiles_data]
            self.logger.info(f"Wczytano {len(self._profiles)} profili.")
            self._validate_profiles()
            return True
            
        except Exception as e:
            self.logger.error(f"Nie udało się wczytać profili z {self.profiles_path}: {e}")
            self._profiles = []
            return False

    def save_profiles(self) -> bool:
        """Zapisuje profile do pliku JSON."""
        try:
            self._validate_profiles()
            
            data = {
                "profiles": [profile.to_dict() for profile in self._profiles],
                "metadata": { "last_updated": datetime.now().isoformat() }
            }
            
            # POPRAWKA: Użycie `self.profiles_path`
            with open(self.profiles_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            os.chmod(self.profiles_path, 0o600)
            self.logger.info(f"Zapisano {len(self._profiles)} profili do {self.profiles_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Nie udało się zapisać profili do {self.profiles_path}: {e}")
            return False

    # Metoda _validate_profiles pozostaje bez zmian
    def _validate_profiles(self) -> None:
        usernames = [p.username for p in self._profiles]
        if len(usernames) != len(set(usernames)):
            self.logger.warning("Znaleziono zduplikowane nazwy użytkowników. To może prowadzić do problemów.")
        
        default_profiles = [p for p in self._profiles if p.default]
        if len(self._profiles) > 0 and len(default_profiles) == 0:
            self._profiles[0].default = True
            self.logger.info("Nie znaleziono domyślnego profilu, ustawiono pierwszy z listy jako domyślny.")
        elif len(default_profiles) > 1:
            for i, profile in enumerate(self._profiles):
                profile.default = (i == 0)
            self.logger.warning("Znaleziono wiele domyślnych profili, zachowano tylko pierwszy.")

    # Pozostałe metody (add_profile, remove_profile, get_profile, etc.)
    # pozostają w większości bez zmian, ponieważ operują już na
    # wewnętrznej liście `self._profiles` i używają poprawionych metod
    # _encrypt/_decrypt i save_profiles. Poniżej ich czyste wersje.

    def add_profile(self, username: str, password: str, description: str = "", is_child_account: bool = False, set_as_default: bool = False) -> bool:
        if any(p.username == username for p in self._profiles):
            self.logger.error(f"Profil o nazwie '{username}' już istnieje.")
            return False
        
        encrypted_password = self._encrypt_password(password)
        
        if set_as_default:
            for p in self._profiles:
                p.default = False
        
        # FIX: The "username" here is actually the login/card number.
        # But the frontend calls add_profile with name, login, pass.
        # The backend endpoint calls add_profile(login, pass, name).
        # So 'username' param receives 'login' (4387717), and 'description' receives 'name' (Aniela).
        
        profile = UserProfile(
            username=username, # This is the LOGIN (card number)
            password=encrypted_password, 
            description=description, # This is the NAME (e.g. Aniela)
            is_child_account=is_child_account, 
            default=set_as_default or not self._profiles,
            created=datetime.now().isoformat()
        )
        self._profiles.append(profile)
        return self.save_profiles()

    def remove_profile(self, username: str) -> bool:
        profile_to_remove = self.get_profile(username)
        if not profile_to_remove:
            return False
        
        was_default = profile_to_remove.default
        self._profiles = [p for p in self._profiles if p.username != username]
        
        if was_default and self._profiles:
            self._profiles[0].default = True
            
        return self.save_profiles()

    def get_profile(self, username: str) -> Optional[UserProfile]:
        # Search by username (login) OR description (name)
        # This fixes the issue where frontend sends 'Aniela' but backend stores '4387717' as username
        return next((p for p in self._profiles if p.username == username or p.description == username), None)

    def get_all_profiles(self) -> List[UserProfile]:
        return self._profiles.copy()

    def get_default_profile(self) -> Optional[UserProfile]:
        return next((p for p in self._profiles if p.default), None)

    def set_default_profile(self, username: str) -> bool:
        profile = self.get_profile(username)
        if not profile:
            return False
        
        for p in self._profiles:
            p.default = False
        profile.default = True
        return self.save_profiles()

    def get_credentials(self, username: str) -> Optional[Tuple[str, str]]:
        try:
            profile = self.get_profile(username)
            if not profile:
                return None
            
            decrypted_password = self._decrypt_password(profile.password)
            profile.last_used = datetime.now().isoformat()
            self.save_profiles() # Zapisz zaktualizowaną datę ostatniego użycia
            return (profile.username, decrypted_password)
        except Exception as e:
            self.logger.error(f"Nie udało się pobrać danych dla {username}: {e}")
            return None

    def update_profile(self, username: str, new_password: Optional[str] = None, new_description: Optional[str] = None, is_child_account: Optional[bool] = None) -> bool:
        profile = self.get_profile(username)
        if not profile:
            return False
        
        if new_password:
            profile.password = self._encrypt_password(new_password)
        if new_description is not None:
            profile.description = new_description
        if is_child_account is not None:
            profile.is_child_account = is_child_account
            
        return self.save_profiles()

    def has_profiles(self) -> bool:
        return len(self._profiles) > 0