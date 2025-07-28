"""
Medicover Tkinter GUI for Appointment Management
"""
from calendar import Calendar
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, date
from custom_widgets import ChecklistCombobox
import threading
import sys
import os
import json
import time
from profile_manager import ProfileManager
from error_handler import APIRetryExhaustedError
from pathlib import Path
logger = logging.getLogger(__name__)
from medicover_client import LoginRequiredException


class ProfileManagerWindow(tk.Toplevel):
    """
    Okno do zarządzania profilami użytkowników.
    REF: Wyniesione poza klasę MedicoverGUI dla lepszej modularyzacji.
    """
    def __init__(self, master, app, on_change_callback):
        super().__init__(master)
        self.app = app
        self.on_change_callback = on_change_callback

        self.title("Zarządzanie profilami")
        self.geometry("420x320")
        self.resizable(False, False)

        # REF: Ustawienie okna jako modalne (blokuje okno główne)
        self.transient(master)
        self.grab_set()

        self._build_widgets()
        self.refresh_profiles()

    def _build_widgets(self):
        """Tworzy widgety okna zarządzania profilami."""
        self.listbox = tk.Listbox(self, height=10)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btns_frame = tk.Frame(self)
        btns_frame.pack(fill=tk.X, padx=10, pady=2)

        tk.Button(btns_frame, text="Dodaj", command=self.add_profile).pack(side=tk.LEFT, padx=4)
        tk.Button(btns_frame, text="Edytuj", command=self.edit_profile).pack(side=tk.LEFT, padx=4)
        tk.Button(btns_frame, text="Usuń", command=self.delete_profile).pack(side=tk.LEFT, padx=4)
        tk.Button(btns_frame, text="Ustaw domyślny", command=self.set_default).pack(side=tk.LEFT, padx=4)

    def refresh_profiles(self):
        """Odświeża listę profili w listboxie, używając nowego formatu."""
        self.listbox.delete(0, tk.END)
        current_default = self.app.profile_manager.get_default_profile()
        
        for p in self.app.profile_manager.get_all_profiles():
            display_name = self._format_profile_display(p)
            label = f"{display_name} (domyślny)" if current_default and p.username == current_default.username else display_name
            self.listbox.insert(tk.END, label)

    def _ask_credentials(self, title: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Pyta użytkownika o dane logowania, wymuszając podanie wszystkich trzech pól.
        """
        # --- Pętla walidacyjna dla Loginu ---
        while True:
            u = simpledialog.askstring(title, "Login (numer karty Medicover):", parent=self)
            if u is None: return None, None, None
            if u.strip(): break
            messagebox.showwarning("Wymagane dane", "Pole 'Login' nie może być puste.", parent=self)

        # --- Pętla walidacyjna dla Hasła ---
        while True:
            p = simpledialog.askstring(title, "Hasło:", show="*", parent=self)
            if p is None: return None, None, None
            if p: break
            messagebox.showwarning("Wymagane dane", "Pole 'Hasło' nie może być puste.", parent=self)

        # --- Pętla walidacyjna dla Nazwy Konta (dawniej Opis) ---
        while True:
            d = simpledialog.askstring(title, "Twoja nazwa konta (np. Moje konto, Konto dziecka):", parent=self)
            if d is None: return None, None, None
            if d.strip(): break
            messagebox.showwarning("Wymagane dane", "Pole 'Twoja nazwa konta' nie może być puste.", parent=self)
        
        # Zwracamy wszystkie wartości po usunięciu zbędnych spacji
        return u.strip(), p, d.strip()

    def add_profile(self):
        """Dodaje nowy profil użytkownika."""
        u, p, d = self._ask_credentials("Dodaj profil")
        if not u or not p:
            return
        is_child = messagebox.askyesno(
            "Typ Konta",
            "Czy to jest konto dziecka?\n\n(Wybór 'Tak' spowoduje wyświetlenie specjalności pediatrycznych)",
            parent=self
        )
        default = messagebox.askyesno("Domyślny?", "Ustawić profil jako domyślny?", parent=self)
        if self.app.profile_manager.add_profile(u, p, d, is_child_account=is_child, set_as_default=default):
            if default:
                self.app.switch_profile(u)
            self._finalize_operation("Profil dodany pomyślnie.")

    def edit_profile(self):
        """Edytuje wybrany profil, włączając w to zmianę typu konta."""
        sel_username = self._selected_username()
        if not sel_username:
            return

        # Pobierz aktualny stan profilu, aby znać jego obecny typ
        profile = self.app.profile_manager.get_profile(sel_username)
        if not profile:
            messagebox.showerror("Błąd", f"Nie można znaleźć profilu: {sel_username}", parent=self)
            return
        
        # Zapytaj o nowe hasło i opis (bez zmian)
        new_pass = simpledialog.askstring("Edytuj profil", "Nowe hasło (puste = bez zmian):", show="*", parent=self)
        new_desc = simpledialog.askstring("Edytuj profil", "Nowa nazwa (puste = bez zmian):", initialvalue=profile.description, parent=self)

        # NOWA LOGIKA: Zapytaj o zmianę typu konta
        current_status = "TAK" if profile.is_child_account else "NIE"
        
        # Używamy `askyesnocancel` - daje trzy opcje: Tak, Nie, Anuluj
        # Jeśli użytkownik kliknie "Anuluj", nie zmieniamy nic.
        is_child_answer = messagebox.askyesnocancel(
            "Edytuj Typ Konta",
            f"Czy to jest konto dziecka?\n\nAktualne ustawienie: {current_status}\n\n(Wybór 'Tak' pokaże specjalności pediatryczne)",
            parent=self
        )
        
        # Przekonwertuj odpowiedź (True/False/None) na nową wartość flagi
        new_is_child_value = None
        if is_child_answer is not None: # Jeśli nie kliknięto "Anuluj"
            new_is_child_value = is_child_answer

        # Wywołaj metodę aktualizującą z menedżera profili
        # Przekazujemy None, jeśli użytkownik nie chciał zmieniać hasła/opisu
        if self.app.profile_manager.update_profile(
            sel_username, 
            new_password=new_pass or None, 
            new_description=new_desc if new_desc is not None else None,
            is_child_account=new_is_child_value
        ):
            self._finalize_operation("Profil zaktualizowano.")

    def delete_profile(self):
        """Usuwa wybrany profil."""
        sel = self._selected_username()
        if not sel:
            return
        if messagebox.askyesno("Potwierdź", f"Usunąć profil \"{sel}\"?", parent=self):
            if self.app.profile_manager.remove_profile(sel):
                if sel == self.app.get_current_profile():
                    default_profile = self.app.profile_manager.get_default_profile()
                    if default_profile:
                        self.app.switch_profile(default_profile.username)
                self._finalize_operation("Profil usunięty.")

    def set_default(self):
        """Ustawia wybrany profil jako domyślny."""
        sel = self._selected_username()
        if not sel:
            return
        if self.app.profile_manager.set_default_profile(sel):
            self.app.switch_profile(sel)
            self._finalize_operation("Ustawiono profil domyślny.")

    def _selected_username(self) -> Optional[str]:
        """Zwraca czysty username zaznaczonego na liście profilu."""
        if not self.listbox.curselection():
            messagebox.showwarning("Brak wyboru", "Zaznacz profil na liście.", parent=self)
            return None
        
        selected_display_name = self.listbox.get(self.listbox.curselection()[0])
        # Usuń ewentualny dopisek "(domyślny)"
        clean_display_name = selected_display_name.replace(" (domyślny)", "")
        
        # Wyodrębnij username
        username = clean_display_name
        if " (" in clean_display_name and clean_display_name.endswith(")"):
            username = clean_display_name.split(" (")[-1][:-1]
            
        return username

    def _finalize_operation(self, msg: str):
        """Kończy operację, odświeża widoki i informuje użytkownika."""
        self.refresh_profiles()
        self.on_change_callback()
        messagebox.showinfo("Informacja", msg, parent=self)

    def _format_profile_display(self, profile):
        """Formatuje obiekt profilu do czytelnego stringa."""
        if profile.description:
            return f"{profile.description} ({profile.username})"
        else:
            return profile.username
class ProgressWindow(tk.Toplevel):
    """
    Modalne okno dialogowe z deterministycznym paskiem postępu i etykietą
    statusu, używane podczas procesu logowania.
    """
    def __init__(self, master, title_text="Proszę czekać..."):
        super().__init__(master)
        self.title(title_text)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.status_label = ttk.Label(self, text="Inicjalizacja...", padding=(20, 10))
        self.status_label.pack()
        
        # Używamy deterministycznego paska postępu
        self.progress_bar = ttk.Progressbar(self, mode='determinate', length=300, maximum=100)
        self.progress_bar.pack(padx=20, pady=10)
        
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = master.winfo_y() + (master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def update_progress(self, value: int, text: str):
        """Publiczna metoda do aktualizacji paska postępu i etykiety."""
        if self.winfo_exists():
            self.progress_bar['value'] = value
            self.status_label.config(text=text)
            self.update_idletasks()

    def close_window(self):
        """Zamyka okno."""
        if self.winfo_exists():
            self.grab_release()
            self.destroy()
            
class MedicoverGUI:
    """
    Główna klasa GUI dla aplikacji Medicover.
    """
    # REF: Stałe dla stanów widgetów i innych wartości
    _READONLY = 'readonly'
    _DISABLED = 'disabled'
    _NORMAL = 'normal'
    _SETTINGS_FILE = "gui_settings.json"
    APP_VERSION = "1.0.1"
    COLORS = {
        'primary': '#0078D4',    # Główny niebieski (np. nagłówki, przyciski)
        'primary_light': '#E5F1FB',
        'success': '#107C10',    # Zielony dla akcji (np. rezerwacja)
        'background': '#F3F3F3', # Jasnoszare tło
        'text': '#201F1E',       # Ciemnoszary tekst
        'white': '#FFFFFF',
        'grey': '#7A7A7A'
    }

    def __init__(self, app, config_dir: Path):
        self.app = app
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._SETTINGS_FILE = config_dir / "gui_settings.json"
        self.root = tk.Tk()
        self._setup_styles()
        self.appointments: List[Dict] = []
        self.filtered_appointments: List[Dict] = []
        self._icon_references = []
        self.autobook_enabled = tk.BooleanVar(value=False)
        # Lista zmiennych dla 7 dni tygodnia (Pon-Nd), domyślnie wszystkie zaznaczone
        self.autobook_days_vars = [tk.BooleanVar(value=True) for _ in range(7)]
        # Zmienne dla godziny początkowej i końcowej
        self.autobook_start_hour = tk.IntVar(value=7)
        self.autobook_end_hour = tk.IntVar(value=21)
        # Zmienne dla cyklicznego sprawdzania
        self.cyclic_enabled = tk.BooleanVar(value=False)
        self.cyclic_interval = tk.IntVar(value=self.app.config.get('check_interval_minutes', 5))
        self.cyclic_job_id: Optional[str] = None
        self.countdown_job_id: Optional[str] = None
        self.next_check_time: Optional[datetime] = None
        self.is_quarantined = False
        # Zmienne dla filtrów
        self.filter_specialty = tk.StringVar()

        # Zmienne dla statusu i profilu
        self.status_var = tk.StringVar(value="Gotowy")
        self.count_var = tk.StringVar(value="0 wizyt")
        self.profile_header_var = tk.StringVar(value="Zarządzanie Profilem")
        self.cyclic_header_var = tk.StringVar(value="Automatyczne sprawdzanie: Wyłączone")
        self.autobook_header_var = tk.StringVar(value="Automatyczna Rezerwacja: Wyłączona")
        self._profile_var = tk.StringVar()
        self._sort_column = None # Przechowuje ID ostatnio sortowanej kolumny
        self._sort_direction = False # False = rosnąco, True = malejąco
        self.setup_window()
        self.setup_widgets()
        last_active_profile_name = None
        try:
            with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                all_settings = json.load(f)
                last_active_profile_name = all_settings.get("last_active_profile")
        except (FileNotFoundError, json.JSONDecodeError):
            pass # Ignorujemy błędy, jeśli plik nie istnieje

        # Jeśli nie ma zapisanego profilu, użyj domyślnego z menedżera profili
        if not last_active_profile_name:
            default_profile = self.app.profile_manager.get_default_profile()
            if default_profile:
                last_active_profile_name = default_profile.username
        
        # Jeśli jakikolwiek profil został znaleziony, przełącz na niego i wczytaj ustawienia
        if last_active_profile_name:
            self.app.switch_profile(last_active_profile_name)
        
        self._load_gui_settings(last_active_profile_name)
        # --- KONIEC NOWEJ LOGIKI ---
        
        try:
            profiles = self.app.profile_manager.get_all_profiles()
            display_names = [self._format_profile_display(p) for p in profiles]
            self._profile_combobox['values'] = display_names
            self._update_profile_label()
        except Exception as e:
            self.logger.error(f"Błąd inicjalizacji listy profili: {e}", exc_info=True)
        # Usunęliśmy stąd `_populate_filter_options()`
        self.root.after(100, self.perform_initial_login)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def run(self):
        """Uruchamia główną pętlę GUI."""
        self.logger.info("Uruchamianie GUI Medicover Appointment Finder")
        self.root.mainloop()

    # ===================================================================
    # LIFECYCLE & INITIALIZATION
    # ===================================================================

    def _setup_styles(self):
        """Konfiguruje wszystkie niestandardowe style dla aplikacji."""
        style = ttk.Style()
        style.theme_use('clam')

        # --- Style globalne ---
        style.configure('.', background=self.COLORS['background'], foreground=self.COLORS['text'], font=('Segoe UI', 9))
        style.configure('TFrame', background=self.COLORS['background'])
        style.configure('TLabel', background=self.COLORS['background'])
        style.configure('TCheckbutton', background=self.COLORS['background'])

        # --- Ramki z tytułem ---
        style.configure('TLabelFrame', background=self.COLORS['background'], borderwidth=1, relief="solid")
        style.configure('TLabelFrame.Label', background=self.COLORS['background'], foreground=self.COLORS['primary'], font=('Segoe UI', 10, 'bold'))

        # --- Etykiety specjalne ---
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), foreground=self.COLORS['primary'])
        style.configure('Info.TLabel', foreground=self.COLORS['grey'])

        # --- Przyciski ---
        style.configure('TButton', font=('Segoe UI', 9, 'bold'), foreground=self.COLORS['white'], background=self.COLORS['primary'], borderwidth=0)
        style.map('TButton',
                background=[('active', '#005A9E'), ('disabled', self.COLORS['grey'])])
        
        style.configure('Success.TButton', background=self.COLORS['success'])
        style.map('Success.TButton', background=[('active', '#0A530A')])

        # --- Tabela (Treeview) ---
        style.configure('Treeview', rowheight=25, fieldbackground=self.COLORS['white'])
        # Dedykowany styl dla klikalnej
        style.configure('Calendar.TButton', 
                        padding=0, 
                        font=('Segoe UI', 10), 
                        width=2, 
                        anchor='center')
        
        # Dodajemy obramowanie do nagłówków, aby je rozdzielić
        style.configure('Treeview.Heading', 
                        font=('Segoe UI', 10, 'bold'), 
                        background=self.COLORS['primary'], 
                        foreground=self.COLORS['white'], 
                        relief='raised', 
                        borderwidth=1)
        style.map('Treeview.Heading', 
                background=[('active', '#005A9E')],
                relief=[('active', 'sunken')])

        style.configure('Highlight.TLabel', foreground='red', font=('Segoe UI', 9, 'bold'), background=self.COLORS['background'])

    def on_closing(self):
        """Obsługuje zamknięcie aplikacji, zapisując ustawienia."""
        self.logger.info("Zamykanie aplikacji GUI...")
        self.stop_cyclic_check()
        self._save_gui_settings() # Wywołanie nowej metody zapisu
        self.root.destroy()
        sys.exit(0)

    def _save_gui_settings(self):
        """
        Zapisuje ustawienia GUI dla aktualnie aktywnego profilu oraz informację,
        który profil był ostatnio aktywny.
        """
        username = self.app.get_current_profile()
        if not username:
            self.logger.warning("Brak aktywnego profilu, pomijam zapisywanie ustawień GUI.")
            return

        # Wczytaj całą istniejącą bazę ustawień
        all_settings = {"last_active_profile": None, "profiles_settings": {}}
        try:
            with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Upewnij się, że wczytane dane mają poprawną strukturę
                if isinstance(loaded_data, dict):
                    all_settings = loaded_data
        except (FileNotFoundError, json.JSONDecodeError):
            self.logger.info("Plik ustawień GUI nie istnieje lub jest uszkodzony. Tworzenie nowego.")

        # Zbierz aktualne ustawienia z GUI
        current_user_settings = {
            "cyclic_check_interval": self.cyclic_interval.get(),
            "filter_specialty": self.filter_specialty.get(),
            "filter_doctors": self.doctor_combo.get_checked_items(),
            "filter_clinics": self.clinic_combo.get_checked_items(),
            "filter_date_from": self.date_from_entry.get(),
            "filter_date_to": self.date_to_entry.get(),
            "autobook_enabled": self.autobook_enabled.get(),
            "autobook_days": [var.get() for var in self.autobook_days_vars],
            "autobook_start_hour": self.autobook_start_hour.get(),
            "autobook_end_hour": self.autobook_end_hour.get()
        }
        
        # Zaktualizuj słownik z ustawieniami profili
        if "profiles_settings" not in all_settings:
            all_settings["profiles_settings"] = {}
        all_settings["profiles_settings"][username] = current_user_settings
        
        # Zaktualizuj informację o ostatnio aktywnym profilu
        all_settings["last_active_profile"] = username

        # Zapisz całą, zaktualizowaną strukturę z powrotem do pliku
        try:
            with open(self._SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_settings, f, indent=4)
            self.logger.info(f"Ustawienia GUI dla profilu '{username}' zostały zapisane.")
        except Exception as e:
            self.logger.error(f"Nie udało się zapisać ustawień GUI: {e}")

    def _load_gui_settings(self, profile_name: Optional[str]):
        """
        Wczytuje ustawienia GUI dla podanego profilu i aktualizuje interfejs.
        """
        self.logger.info(f"Wczytywanie ustawień GUI dla profilu: {profile_name}")
        
        settings = {}
        if profile_name:
            try:
                with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    all_settings = json.load(f)
                # Pobierz ustawienia dla konkretnego profilu zagnieżdżone w 'profiles_settings'
                settings = all_settings.get("profiles_settings", {}).get(profile_name, {})
            except (FileNotFoundError, json.JSONDecodeError):
                self.logger.info("Plik ustawień nie istnieje. Używanie wartości domyślnych.")
        
        # Reszta metody pozostaje taka sama, ponieważ operuje już na słowniku 'settings'
        # ... (cały kod od "KROK 1: Wypełnij listy opcji..." do końca metody)
        self._populate_filter_options()
        saved_specialty = settings.get("filter_specialty")
        if saved_specialty and saved_specialty in self.specialty_combo['values']:
            self.filter_specialty.set(saved_specialty)
        self.on_specialty_selected()
        self.doctor_combo.set_checked_items(settings.get("filter_doctors", []))
        self.clinic_combo.set_checked_items(settings.get("filter_clinics", []))
        self.date_from_entry.delete(0, tk.END)
        self.date_to_entry.delete(0, tk.END)
        self.date_from_entry.insert(0, settings.get("filter_date_from", datetime.now().strftime('%Y-%m-%d')))
        self.date_to_entry.insert(0, settings.get("filter_date_to", ""))
        self.cyclic_interval.set(settings.get("cyclic_check_interval", 5))
        self.autobook_enabled.set(settings.get("autobook_enabled", False))
        saved_days = settings.get("autobook_days", [True]*7)
        if len(saved_days) == 7:
            for i, val in enumerate(saved_days):
                self.autobook_days_vars[i].set(val)
        self.autobook_start_hour.set(settings.get("autobook_start_hour", 7))
        self.autobook_end_hour.set(settings.get("autobook_end_hour", 21))
        self._update_autobook_header()

    def _execute_login_with_progress_bar(self, on_success_callback=None):
        if not self.app.client:
            self.logger.error("Próba logowania bez klienta.")
            messagebox.showerror("Błąd krytyczny", "Klient aplikacji nie jest gotowy.")
            return

        self.logger.info("Uruchamianie procesu logowania z inteligentnym paskiem postępu...")
        self.status_var.set("Logowanie do systemu Medicover...")
        
        progress_win = ProgressWindow(self.root, title_text="Logowanie w toku...")

        def login_worker():
            try:
                # Przekaż metodę okna postępu jako callback do logiki klienta
                self.app.client.config_data['progress_callback'] = progress_win.update_progress
                
                username = self.app.client.username
                password = self.app.client.password
                success = self.app.client.login(username, password)
                
                # Po zakończeniu, ustaw pasek na 100%
                if success:
                    progress_win.update_progress(100, "Zalogowano pomyślnie!")
                    time.sleep(0.5) # Krótka pauza, aby użytkownik zobaczył sukces
                
                self.root.after(0, on_login_complete, success)
            except Exception as e:
                self.logger.error(f"Krytyczny błąd w wątku logowania: {e}", exc_info=True)
                self.root.after(0, on_login_complete, False)

        def on_login_complete(success: bool):
            progress_win.close_window()
            # Usuń callback, aby uniknąć problemów z referencjami
            if 'progress_callback' in self.app.client.config_data:
                del self.app.client.config_data['progress_callback']

            if success:
                self.logger.info("Logowanie zakończone sukcesem.")
                self.status_var.set("Zalogowano pomyślnie.")
                if on_success_callback:
                    on_success_callback()
            else:
                self.logger.error("Logowanie nie powiodło się.")
                self.status_var.set("Błąd logowania.")
                messagebox.showerror("Błąd logowania", "Nie udało się zalogować. Sprawdź dane lub spróbuj ponownie.")

        threading.Thread(target=login_worker, daemon=True).start()
        
    def perform_initial_login(self):
        """
        Inicjuje logowanie przy starcie aplikacji, jeśli profil jest skonfigurowany.
        W przeciwnym razie, prosi użytkownika o stworzenie profilu.
        """
        if self.app.client:
            # Standardowe działanie: jest klient, więc się logujemy
            self._execute_login_with_progress_bar(on_success_callback=self.search_appointments_from_gui)
        else:
            # NOWA LOGIKA: Aplikacja wystartowała bez profilu
            self.logger.warning("Klient nie jest zainicjalizado. Logowanie początkowe pominięte.")
            self.status_var.set("Witaj! Proszę, stwórz swój pierwszy profil.")
            messagebox.showinfo(
                "Witaj w Medicover Appointment Finder!",
                "Wygląda na to, że uruchamiasz aplikację po raz pierwszy.\n\nPrzejdź do sekcji 'Zarządzanie profilem', aby dodać swoje konto Medicover i rozpocząć wyszukiwanie."
            )

    # ===================================================================
    # UI SETUP
    # ===================================================================

    def setup_window(self):
        """Konfiguruje główne okno aplikacji."""
        self.root.title(f"Medicover Appointment Finder v{self.APP_VERSION}")
        self.root.geometry("1200x850")
        self.root.minsize(1000, 700)
        self.root.configure(background=self.COLORS['background'])
        self.root.eval('tk::PlaceWindow . center')

# --- Wklej ten kod w miejsce starej metody setup_widgets w gui.py ---

    def setup_widgets(self):
        """Tworzy i rozmieszcza wszystkie widgety aplikacji."""
        self.create_status_bar(self.root)
        mainframe = ttk.Frame(self.root, padding="10")
        mainframe.pack(side='top', fill='both', expand=True, padx=5, pady=5)

        title_label = ttk.Label(mainframe, text="Medicover Appointment Finder", style='Header.TLabel')
        title_label.pack(pady=(0, 10))

        # --- Sekcja Zarządzania Profilem (zwijana) ---
        profile_content, _ = self._create_collapsible_frame(mainframe, self.profile_header_var)
        self._build_profile_panel(profile_content)

        # --- Sekcja Automatycznego Sprawdzania (zwijana) ---
        cyclic_content, _ = self._create_collapsible_frame(mainframe, self.cyclic_header_var)
        self._build_cyclic_panel(cyclic_content)

        # --- Sekcja Automatycznej Rezerwacji (zwijana) ---
        autobook_content, self.autobook_title_label = self._create_collapsible_frame(mainframe, self.autobook_header_var)
        self._build_autobook_panel(autobook_content)

        # --- Panele, które są zawsze widoczne ---
        self.create_filter_panel(mainframe)
        self.create_button_panel(mainframe)
        self.create_appointments_table(mainframe)

    def create_cyclic_panel(self, parent):
        """Tworzy panel konfiguracji cyklicznego sprawdzania."""
        cyclic_frame = ttk.LabelFrame(parent, text="Automatyczne sprawdzanie", padding=10)
        cyclic_frame.pack(fill='x', pady=5)

        control_row = ttk.Frame(cyclic_frame)
        control_row.pack(fill='x')

        ttk.Checkbutton(
            control_row, text="Włącz automatyczne sprawdzanie co",
            variable=self.cyclic_enabled, command=self.toggle_cyclic_check
        ).grid(row=0, column=0, padx=(0, 5), sticky='w')

        ttk.Spinbox(
            control_row, from_=1, to=120, width=5,
            textvariable=self.cyclic_interval, command=self.update_cyclic_interval
        ).grid(row=0, column=1, padx=(0, 5))

        ttk.Label(control_row, text="minut").grid(row=0, column=2, padx=(0, 10))

        self.cyclic_status_var = tk.StringVar(value="Automatyczne sprawdzanie wyłączone.")
        ttk.Label(cyclic_frame, textvariable=self.cyclic_status_var, style='Info.TLabel').pack(pady=(5, 0), anchor='w')


    def _on_date_from_changed(self, event=None):
        """Wywoływana po zmianie daty 'od', czyści datę 'do'."""
        self.logger.debug("Data 'od' zmieniona, czyszczenie daty 'do'.")
        self.date_to_entry.delete(0, tk.END)

    def create_filter_panel(self, parent):
        """Tworzy panel filtrów z wyrównanymi i ujednoliconymi szerokościami."""
        filter_frame = ttk.LabelFrame(parent, text="Kryteria wyszukiwania", padding=10)
        filter_frame.pack(fill='x', pady=5)
        
        # --- Rząd 1: Specjalność, Lekarze, Placówki ---
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill='x', pady=(0, 5))

        # NOWOŚĆ: Konfiguracja kolumn siatki, aby miały równą wagę i minimalny rozmiar
        # To jest klucz do równego rozłożenia elementów.
        row1.grid_columnconfigure(1, weight=1, minsize=180)
        row1.grid_columnconfigure(3, weight=1, minsize=180)
        row1.grid_columnconfigure(5, weight=1, minsize=180)

        # Etykieta Specjalność
        ttk.Label(row1, text="Specjalność:").grid(row=0, column=0, padx=(0, 5), sticky='w')
        # ZMIANA: Używamy sticky='ew', aby pole rozciągnęło się na całą szerokość kolumny
        self.specialty_combo = ttk.Combobox(row1, textvariable=self.filter_specialty, width=25, state=self._READONLY)
        self.specialty_combo.grid(row=0, column=1, padx=(0, 10), sticky='ew')
        self.specialty_combo.bind("<<ComboboxSelected>>", self.on_specialty_selected)
        
        # Etykieta Lekarze
        ttk.Label(row1, text="Lekarze:").grid(row=0, column=2, padx=(10, 5), sticky='w')
        # ZMIANA: Używamy sticky='ew'
        self.doctor_combo = ChecklistCombobox(row1)
        self.doctor_combo.grid(row=0, column=3, padx=(0, 10), sticky="ew")
        
        # Etykieta Placówki
        ttk.Label(row1, text="Placówki:").grid(row=0, column=4, padx=(10, 5), sticky='w')
        # ZMIANA: Używamy sticky='ew'
        self.clinic_combo = ChecklistCombobox(row1)
        self.clinic_combo.grid(row=0, column=5, sticky="ew")

        # --- Rząd 2: Daty i Przyciski ---
        row2 = ttk.Frame(filter_frame)
        row2.pack(fill='x', pady=(5, 0))

        # --- Definicja elementów ---
        ttk.Label(row2, text="Data od:").grid(row=0, column=0, padx=(0, 5), sticky='w')

        self.date_from_entry = ttk.Entry(row2, width=12)
        self.date_from_entry.grid(row=0, column=1)

        ttk.Button(row2, text="🗓️", width=3, command=lambda: self._open_calendar(self.date_from_entry), style='Calendar.TButton').grid(row=0, column=2, padx=(2, 10))

        ttk.Label(row2, text="Data do:").grid(row=0, column=3, padx=(10, 5), sticky='w')

        self.date_to_entry = ttk.Entry(row2, width=12)
        self.date_to_entry.grid(row=0, column=4)

        ttk.Button(row2, text="🗓️", width=3, command=lambda: self._open_calendar(self.date_to_entry), style='Calendar.TButton').grid(row=0, column=5, padx=(2, 10))

        self.search_button = ttk.Button(row2, text="Wyszukaj", command=lambda: self.search_appointments_from_gui(is_background_check=False))
        self.search_button.grid(row=0, column=6, padx=(20, 5))

        self.clear_button = ttk.Button(row2, text="Wyczyść filtry", command=self.clear_filters)
        self.clear_button.grid(row=0, column=7, padx=(0, 0))

        # Ta kolumna (numer 8) zajmie całą pozostałą wolną przestrzeń,
        # "dociskając" wszystkie poprzednie elementy (0-7) do lewej strony.
        row2.grid_columnconfigure(8, weight=1) # type: ignore
        
    def create_button_panel(self, parent):
        """Tworzy panel z przyciskami akcji."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill='x', pady=10)
        
        self.book_button = ttk.Button(button_frame, text="Zarezerwuj wybraną", command=self.book_selected_appointment, style='Success.TButton')
        self.book_button.pack(side='left', padx=(0, 10))
        
        ttk.Button(button_frame, text="Eksportuj do pliku", command=self.export_appointments).pack(side='left', padx=(0, 10))


    def create_appointments_table(self, parent):
        """Tworzy tabelę (Treeview) z wizytami."""
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill='both', expand=True, pady=5)
        columns = ('date', 'time', 'doctor', 'specialty', 'clinic')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)
        self.tree.tag_configure('oddrow', background=self.COLORS['primary_light'])
        self.tree.tag_configure('evenrow', background=self.COLORS['white'])
        self.tree.heading('date', text='Data', anchor='center')
        self.tree.heading('time', text='Godzina', anchor='center')
        self.tree.heading('doctor', text='Lekarz', anchor='w')
        self.tree.heading('specialty', text='Specjalność', anchor='w')
        self.tree.heading('clinic', text='Placówka', anchor='w')

        self.tree.column('date', width=100, anchor='center', stretch=False)
        self.tree.column('time', width=80, anchor='center', stretch=False)
        self.tree.column('doctor', width=220, anchor='w')
        self.tree.column('specialty', width=180, anchor='w')
        self.tree.column('clinic', width=320, anchor='w')

        v_scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        self.tree.bind('<Button-1>', self._sort_by_column)
        self.tree.bind('<Double-1>', self.on_appointment_double_click)

    def create_status_bar(self, parent):
        """Tworzy dolny pasek statusu oraz stopkę z zastrzeżeniem i numerem wersji."""
        # --- Główny pasek statusu (bez zmian) ---
        status_frame = ttk.Frame(parent, relief='sunken', padding=(2, 2))
        ttk.Label(status_frame, textvariable=self.status_var, style='Info.TLabel').pack(side='left')
        ttk.Label(status_frame, textvariable=self.count_var, style='Info.TLabel').pack(side='right')

        # --- Stopka z disclaimerem i wersją ---
        # Tworzymy dedykowaną ramkę (kontener) dla stopki
        footer_frame = ttk.Frame(parent, padding=(2, 2)) 

        # Etykieta z zastrzeżeniem (disclaimer) - po lewej stronie
        disclaimer_text = "Aplikacja dostarczana jest 'tak jak jest'. Użytkownik korzysta z niej na własną odpowiedzialność."
        disclaimer_label = ttk.Label(
            footer_frame, 
            text=disclaimer_text, 
            style='Info.TLabel'
        )
        disclaimer_label.pack(side='left')

        # Etykieta z numerem wersji - po prawej stronie
        version_label = ttk.Label(
            footer_frame, 
            text=f"Wersja {self.APP_VERSION}", 
            style='Info.TLabel'
        )
        version_label.pack(side='right')

        # --- Pakowanie wszystkich elementów w poprawnej kolejności ---
        
        # 1. Pakujemy stopkę na samym dole.
        footer_frame.pack(side='bottom', fill='x')
        
        # 2. Pakujemy separator tuż nad stopką.
        ttk.Separator(parent, orient='horizontal').pack(side='bottom', fill='x', padx=2)

        # 3. Pakujemy główny pasek statusu nad separatorem.
        status_frame.pack(side='bottom', fill='x')

    def create_autobook_panel(self, parent):
        """Tworzy panel konfiguracji automatycznej rezerwacji."""
        autobook_frame = ttk.LabelFrame(parent, text="Automatyczna Rezerwacja (Funkcja Eksperymentalna)", padding=10)
        autobook_frame.pack(fill='x', pady=5)

        # --- Główny włącznik ---
        self.autobook_checkbox = ttk.Checkbutton(
            autobook_frame,
            text="Włącz automatyczne rezerwowanie pierwszej znalezionej wizyty",
            variable=self.autobook_enabled,
            command=self._on_autobook_toggle
        )
        self.autobook_checkbox.pack(anchor='w', pady=(0, 10))

        # --- Ramka na filtry szczegółowe ---
        details_frame = ttk.Frame(autobook_frame)
        details_frame.pack(fill='x', padx=5)

        # --- Sekcja Dni Tygodnia ---
        days_frame = ttk.Frame(details_frame)
        days_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(days_frame, text="Dni tygodnia:").pack(side='left', padx=(0, 10))
        day_labels = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]
        self.autobook_day_checkboxes = []
        for i, label in enumerate(day_labels):
            cb = ttk.Checkbutton(days_frame, text=label, variable=self.autobook_days_vars[i])
            cb.pack(side='left')
            self.autobook_day_checkboxes.append(cb)

        # --- Sekcja Przedziału Godzinowego ---
        hours_frame = ttk.Frame(details_frame)
        hours_frame.pack(fill='x')

        ttk.Label(hours_frame, text="Przedział godzinowy:").pack(side='left', padx=(0, 10))
        
        ttk.Label(hours_frame, text="od:").pack(side='left', padx=(0, 5))
        self.autobook_start_spinbox = ttk.Spinbox(hours_frame, from_=0, to=23, width=3, textvariable=self.autobook_start_hour)
        self.autobook_start_spinbox.pack(side='left', padx=(0, 15))

        ttk.Label(hours_frame, text="do:").pack(side='left', padx=(0, 5))
        self.autobook_end_spinbox = ttk.Spinbox(hours_frame, from_=0, to=23, width=3, textvariable=self.autobook_end_hour)
        self.autobook_end_spinbox.pack(side='left')

        # --- Lista wszystkich widgetów do zarządzania stanem ---
        self.autobook_widgets = [
            self.autobook_checkbox,
            self.autobook_start_spinbox,
            self.autobook_end_spinbox
        ] + self.autobook_day_checkboxes

        # Ustaw stan początkowy
        self._update_autobook_widgets_state()

    def _update_autobook_widgets_state(self):
        """Włącza lub wyłącza wszystkie widgety w panelu auto-rezerwacji."""
        if self.cyclic_enabled.get():
            new_state = self._NORMAL
        else:
            new_state = self._DISABLED
            self.autobook_enabled.set(False)

        for widget in self.autobook_widgets:
            widget.config(state=new_state)

        # ZMIANA: Usuwamy starą logikę i zastępujemy ją wywołaniem nowej metody
        self._update_autobook_header()    

    def _build_profile_panel(self, parent):
        """Buduje zawartość panelu profilu."""
        ttk.Label(parent, text="Aktywny profil:").grid(row=0, column=0, padx=(0, 5), sticky='w')
        ttk.Label(parent, textvariable=self._profile_var, foreground=self.COLORS['primary'], font=('Segoe UI', 9, 'bold')).grid(row=0, column=1, padx=(0, 20), sticky='w')
        
        ttk.Label(parent, text="Przełącz na:").grid(row=0, column=2, padx=(10, 5), sticky='w')
        self._profile_combobox = ttk.Combobox(parent, state=self._READONLY, width=35)
        self._profile_combobox.grid(row=0, column=3, sticky='ew')
        self._profile_combobox.bind("<<ComboboxSelected>>", self._on_profile_selected)

        ttk.Button(parent, text="Zarządzaj Profilami...", command=self._open_profile_manager).grid(row=0, column=4, padx=(10, 0))
        
        parent.grid_columnconfigure(3, weight=1)

    def _build_cyclic_panel(self, parent):
        """Buduje zawartość panelu cyklicznego sprawdzania."""
        ttk.Checkbutton(
            parent, text="Włącz automatyczne sprawdzanie co",
            variable=self.cyclic_enabled, command=self.toggle_cyclic_check
        ).grid(row=0, column=0, padx=(0, 5), sticky='w')

        ttk.Spinbox(
            parent, from_=1, to=120, width=5,
            textvariable=self.cyclic_interval, command=self.update_cyclic_interval
        ).grid(row=0, column=1, padx=(0, 5))

        ttk.Label(parent, text="minut").grid(row=0, column=2, padx=(0, 10))

    def _build_autobook_panel(self, parent):
        """Buduje zawartość panelu automatycznej rezerwacji."""
        self.autobook_checkbox = ttk.Checkbutton(
            parent,
            text="Włącz automatyczne rezerwowanie pierwszej znalezionej wizyty",
            variable=self.autobook_enabled,
            command=self._on_autobook_toggle
        )
        self.autobook_checkbox.pack(anchor='w', pady=(0, 10))

        details_frame = ttk.Frame(parent)
        details_frame.pack(fill='x', padx=5)
        
        days_frame = ttk.Frame(details_frame)
        days_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(days_frame, text="Dni tygodnia:").pack(side='left', padx=(0, 10))
        day_labels = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]
        self.autobook_day_checkboxes = []
        for i, label in enumerate(day_labels):
            cb = ttk.Checkbutton(days_frame, text=label, variable=self.autobook_days_vars[i])
            cb.pack(side='left')
            self.autobook_day_checkboxes.append(cb)

        hours_frame = ttk.Frame(details_frame)
        hours_frame.pack(fill='x')
        ttk.Label(hours_frame, text="Przedział godzinowy:").pack(side='left', padx=(0, 10))
        
        ttk.Label(hours_frame, text="od:").pack(side='left', padx=(0, 5))
        self.autobook_start_spinbox = ttk.Spinbox(hours_frame, from_=0, to=23, width=3, textvariable=self.autobook_start_hour)
        self.autobook_start_spinbox.pack(side='left', padx=(0, 15))

        ttk.Label(hours_frame, text="do:").pack(side='left', padx=(0, 5))
        self.autobook_end_spinbox = ttk.Spinbox(hours_frame, from_=0, to=23, width=3, textvariable=self.autobook_end_hour)
        self.autobook_end_spinbox.pack(side='left')

        self.autobook_widgets = [
            self.autobook_checkbox, self.autobook_start_spinbox, self.autobook_end_spinbox
        ] + self.autobook_day_checkboxes
        self._update_autobook_widgets_state()

    # ===================================================================
    # UI UPDATES & POPULATION
    # ===================================================================

    def _update_gui_with_appointments(self, appointments: Optional[List[Dict]], source: str = "Odświeżenie"):
        """
        Centralna metoda do aktualizacji GUI. Stosuje sortowanie,
        aktualizuje dane i obsługuje błędy.
        """
        try:
            self.logger.debug(f"--- _update_gui_with_appointments wywołane ze źródła: {source} ---")
            if not appointments:
                self.logger.debug("Otrzymano pustą listę wizyt. Czyszczenie tabeli.")
            else:
                self.logger.debug(f"Otrzymano {len(appointments)} wizyt do przetworzenia.")

            if self._sort_column and appointments:
                self.logger.debug(f"Wykryto aktywne sortowanie (kolumna={self._sort_column}). Przystępuję do sortowania.")
                key_map = {
                    '#1': ('appointmentDate',), '#2': ('appointmentDate',),
                    '#3': ('doctor', 'name'), '#4': ('specialty', 'name'),
                    '#5': ('clinic', 'name')
                }
                sort_path = key_map.get(self._sort_column)

                if sort_path:
                    def safe_getter(item):
                        value = item
                        for key in sort_path: value = value.get(key, {})
                        return value if not isinstance(value, dict) else ""
                    
                    # LOGOWANIE PRZED I PO SORTOWANIU
                    self.logger.debug(f"Przed sortowaniem (pierwsze 3): {[safe_getter(a) for a in appointments[:3]]}")
                    appointments.sort(key=safe_getter, reverse=self._sort_direction)
                    self.logger.debug(f"Po sortowaniu (pierwsze 3): {[safe_getter(a) for a in appointments[:3]]}")
                else:
                    self.logger.debug("Nie znaleziono ścieżki sortowania dla aktywnej kolumny. Pomijam sortowanie.")
            else:
                self.logger.debug("Brak aktywnego sortowania lub brak danych. Pomijam sortowanie.")

            if appointments:
                if source != "Sortowanie": self.appointments = appointments
                self.filtered_appointments = appointments.copy()
                count = len(appointments)
                visits_word = self._pluralize_visits(count)
                self.status_var.set(f"{source}: Znaleziono {count} {visits_word} ({datetime.now():%H:%M:%S})")
            else:
                if source != "Sortowanie": self.appointments = []
                self.filtered_appointments = []
                count = 0
                self.status_var.set(f"{source}: Brak dostępnych wizyt.")

            self.populate_table()
            visits_word = self._pluralize_visits(count)
            self.count_var.set(f"{count} {visits_word}")

        except Exception as e:
            self.logger.error(f"Błąd podczas aktualizacji GUI danymi o wizytach: {e}", exc_info=True)
            self.status_var.set("Błąd krytyczny podczas aktualizacji interfejsu.")

    def _update_autobook_header(self):
        """Aktualizuje tekst i styl nagłówka sekcji auto-rezerwacji."""
        if self.autobook_enabled.get():
            self.autobook_header_var.set("Automatyczna Rezerwacja: Włączona")
            self.autobook_title_label.config(style='Highlight.TLabel')
        else:
            self.autobook_header_var.set("Automatyczna Rezerwacja: Wyłączona")
            self.autobook_title_label.config(style='Info.TLabel')

    def on_specialty_selected(self, event=None):
        """
        Filtruje listę lekarzy w widżecie ChecklistCombobox na podstawie
        wybranej specjalności.
        """
        selected_specialty = self.filter_specialty.get()
        all_doctors_data = self.app.doctor_manager.get_all_doctors_data()
        
        filtered_doctor_names = []

        # Jeśli wybrano "Wszystkie" specjalności, pokaż wszystkich lekarzy
        if not selected_specialty or selected_specialty == "Wszystkie":
            filtered_doctor_names = sorted(list(all_doctors_data.keys()))
        else:
            # W przeciwnym razie, filtruj lekarzy po ID specjalności
            spec_ids = self.app.specialty_manager.get_ids_by_name(selected_specialty)
            if not spec_ids:
                self.doctor_combo.set_items([]) # Ustaw pustą listę, jeśli specjalność nie ma ID
                return

            try:
                spec_ids_set = set(map(int, spec_ids))
            except (ValueError, TypeError):
                self.logger.error(f"Nieprawidłowe ID w pliku specjalności dla: {selected_specialty}")
                spec_ids_set = set()

            for doc_name, doc_data in all_doctors_data.items():
                doctor_spec_ids_list = doc_data.get('specialty_ids', [])
                try:
                    doctor_spec_ids_set = set(map(int, doctor_spec_ids_list))
                except (ValueError, TypeError):
                    doctor_spec_ids_set = set()

                if not spec_ids_set.isdisjoint(doctor_spec_ids_set):
                    filtered_doctor_names.append(doc_name)
            
            filtered_doctor_names.sort()

        # ZMIANA: Użyj poprawnej metody set_items() zamiast opcji ['values']
        self.doctor_combo.set_items(filtered_doctor_names)
        
    def populate_table(self):
        """Wypełnia tabelę wizytami, aktualizuje nagłówki i stosuje naprzemienne kolory."""
        key_map = {'#1': 'Data', '#2': 'Godzina', '#3': 'Lekarz', '#4': 'Specjalność', '#5': 'Placówka'}
        for col_id, base_text in key_map.items():
            if col_id == self._sort_column:
                arrow = " ▼" if self._sort_direction else " ▲"
                self.tree.heading(col_id, text=base_text + arrow)
            else:
                self.tree.heading(col_id, text=base_text)

        self.tree.delete(*self.tree.get_children())
        for i, appointment in enumerate(self.filtered_appointments):
            tag = 'oddrow' if i % 2 == 0 else 'evenrow'
            date_str, time_str = self.extract_appointment_data(appointment)
            doctor = self.extract_doctor_name(appointment)
            specialty = self.extract_specialty_name(appointment)
            clinic = self.extract_clinic_name(appointment)
            self.tree.insert('', 'end', values=(date_str, time_str, doctor, specialty, clinic), tags=(tag,))

    def _populate_filter_options(self):
        """
        Inteligentnie aktualizuje opcje w filtrach, dostosowując listę
        specjalności do typu aktywnego profilu (dorosły/dziecko).
        """
        self.logger.debug("Odświeżanie opcji w filtrach...")

        # KROK 1: Sprawdź typ bieżącego profilu
        is_child_account = False
        current_username = self.app.get_current_profile()
        if current_username:
            profile = self.app.profile_manager.get_profile(current_username)
            if profile:
                is_child_account = profile.is_child_account
        
        self.logger.info(f"Pobieranie specjalności dla konta {'dziecka' if is_child_account else 'dorosłego'}.")

        # KROK 2: Pobierz przefiltrowaną listę specjalności
        new_specialties = self.app.specialty_manager.get_all_names(is_child_account=is_child_account)
        
        # KROK 3: Zaktualizuj Combobox
        current_selection = self.filter_specialty.get()
        self.specialty_combo['values'] = new_specialties
        
        if current_selection in new_specialties:
            self.filter_specialty.set(current_selection)
        elif new_specialties:
            self.filter_specialty.set(new_specialties[0])
        else:
            # Sytuacja awaryjna: brak dostępnych specjalności
            self.filter_specialty.set("")
            messagebox.showwarning("Brak specjalności", "Nie znaleziono żadnych dostępnych specjalności dla wybranego typu konta.")

        # Aktualizacja lekarzy i placówek (bez zmian)
        all_doctors = self.app.doctor_manager.get_all_names()
        self.doctor_combo.set_items(all_doctors)
        all_clinics = self.app.clinic_manager.get_all_names()
        self.clinic_combo.set_items(all_clinics)
        
    def _clear_gui_view(self):
        """
        Natychmiastowo czyści wszystkie elementy GUI związane z wizytami.
        Daje użytkownikowi natychmiastową informację zwrotną o zmianie.
        """
        self.logger.info("Czyszczenie widoku wizyt w GUI...")
        
        # 1. Wyczyść wewnętrzne listy z danymi
        self.appointments = []
        self.filtered_appointments = []
        
        # 2. Wyczyść tabelę Treeview
        self.populate_table()
        
        # 3. Wyczyść opcje w filtrach
        self._populate_filter_options()
        
        # 4. Zresetuj liczniki
        self.count_var.set("0 wizyt")
        
        # 5. Wyczyść panel szczegółów
        try:
            self.details_text.config(state=self._NORMAL)
            self.details_text.delete(1.0, tk.END)
            self.details_text.config(state=self._DISABLED)
        except Exception:
            pass # Ignoruj błędy, jeśli widget nie istnieje
            

    def _update_countdown_label(self):
        """Aktualizuje etykietę z licznikiem co sekundę."""
        if self.countdown_job_id:
            self.root.after_cancel(self.countdown_job_id)

        if self.cyclic_enabled.get() and self.next_check_time:
            remaining = self.next_check_time - datetime.now()
            if remaining.total_seconds() > 0:
                minutes, seconds = divmod(int(remaining.total_seconds()), 60)
                countdown_text = f"{minutes:02d}:{seconds:02d}"
                self.cyclic_header_var.set(f"Automatyczne sprawdzanie: Włączone (następne za {countdown_text})")
                self.countdown_job_id = self.root.after(1000, self._update_countdown_label)
            else:
                self.cyclic_header_var.set("Automatyczne sprawdzanie: Trwa sprawdzanie...")
        else:
            self.cyclic_header_var.set("Automatyczne sprawdzanie: Wyłączone")

    def _create_collapsible_frame(self, parent, title_var):
        """
        Tworzy uniwersalny, zwijany kontener (akordeon).

        Args:
            parent: Widget nadrzędny.
            title_var: StringVar, który będzie dynamicznie wyświetlany w nagłówku.

        Returns:
            Ramka (Frame), do której można dodawać zawartość sekcji.
        """
        container = ttk.Frame(parent, style='TFrame')
        container.pack(fill='x', pady=(1, 0))

        # --- Nagłówek ---
        header = ttk.Frame(container, style='TFrame')
        header.pack(fill='x', ipady=2)
        
        # Używamy zwykłego Label zamiast Buttona dla ikony, aby uniknąć obramowania
        icon_label = ttk.Label(header, text='[+]', style='Info.TLabel')
        icon_label.pack(side='left', padx=(5, 5))
        
        title_label = ttk.Label(header, textvariable=title_var, style='Info.TLabel', anchor='w')
        title_label.pack(side='left', fill='x', expand=True)

        # --- Ramka na zawartość ---
        content_frame = ttk.Frame(container, padding=10)
        # Domyślnie zawartość jest ukryta
        content_frame.pack_forget()

        def toggle_visibility(event=None):
            if content_frame.winfo_ismapped():
                content_frame.pack_forget()
                icon_label.config(text='[+]')
            else:
                content_frame.pack(fill='x')
                icon_label.config(text='[-]')
        
        # Bindowanie zdarzenia kliknięcia do całego nagłówka
        for widget in [header, icon_label, title_label]:
            widget.bind("<Button-1>", toggle_visibility)

        return content_frame, title_label
    # ===================================================================
    # EVENT HANDLERS
    # ===================================================================

    def on_appointment_double_click(self, event):
        """Obsługuje podwójne kliknięcie na wizytę (rezerwacja)."""
        self.book_selected_appointment()

    def _on_profile_selected(self, event):
            """Obsługuje przełączenie profilu: zapisuje stare i wczytuje nowe ustawienia."""
            old_username = self.app.get_current_profile()
            selected_display_name = self._profile_combobox.get()

            # --- NOWA, ODPORNA LOGIKA: Wyszukanie profilu po nazwie wyświetlanej ---
            new_username = None
            # Przeszukujemy wszystkie profile, aby znaleźć ten, który pasuje do wybranej nazwy.
            # To jest znacznie bezpieczniejsze niż parsowanie stringów.
            for profile in self.app.profile_manager.get_all_profiles():
                if self._format_profile_display(profile) == selected_display_name:
                    new_username = profile.username
                    break # Znaleziono, można przerwać pętlę
            # --------------------------------------------------------------------

            # Sprawdzenie, czy udało się znaleźć username (zabezpieczenie)
            if not new_username:
                self.logger.error(f"Nie udało się znaleźć nazwy użytkownika dla wybranej pozycji: '{selected_display_name}'")
                # Przywróć starą wartość w comboboxie, aby uniknąć niespójności
                if old_username:
                    old_profile = self.app.profile_manager.get_profile(old_username)
                    if old_profile:
                        self._profile_combobox.set(self._format_profile_display(old_profile))
                return

            if new_username == old_username:
                return

            # Reszta logiki pozostaje bez zmian
            if messagebox.askyesno("Przełącz profil", f"Czy na pewno chcesz przełączyć na profil '{selected_display_name}'?"):
                self._save_gui_settings()

                if not self.app.switch_profile(new_username):
                    messagebox.showerror("Błąd", f"Nie udało się przełączyć na profil '{selected_display_name}'.")
                    if old_username:
                        old_profile = self.app.profile_manager.get_profile(old_username)
                        if old_profile:
                            self._profile_combobox.set(self._format_profile_display(old_profile))
                    return

                self._load_gui_settings(new_username)
                self._update_profile_label()
                self.search_appointments_from_gui()

    def _on_profiles_changed(self):
        """Callback wywoływany po zmianach w menedżerze profili."""
        try:
            profiles = self.app.profile_manager.get_all_profiles()
            display_names = [self._format_profile_display(p) for p in profiles]
            self._profile_combobox['values'] = display_names
            self._update_profile_label()
        except Exception as e:
            self.logger.error(f"Błąd odświeżania listy profili po zmianach: {e}", exc_info=True)
        
        # Wyszukiwanie wizyt pozostaje bez zmian
        self.search_appointments_from_gui()

    def _on_autobook_toggle(self):
        """Wyświetla ostrzeżenie i aktualizuje stan po przełączeniu auto-rezerwacji."""
        if self.autobook_enabled.get():
            confirmed = messagebox.askyesno(
                "Potwierdzenie - Ryzykowna Operacja",
                "UWAGA!\n\nWłączasz tryb automatycznej rezerwacji...",
                icon='warning'
            )
            if not confirmed:
                self.autobook_enabled.set(False)
        
        # ZMIANA: Wywołujemy naszą nową, centralną metodę aktualizującą
        self._update_autobook_header()

    # ===================================================================
    # CYCLIC CHECKING LOGIC
    # ===================================================================

    def _enter_quarantine(self):
        """Wprowadza aplikację w 10-minutowy tryb kwarantanny po błędzie 429."""
        if self.is_quarantined:
            return # Już jesteśmy w kwarantannie

        self.is_quarantined = True
        self.logger.critical("WCHODZĘ W TRYB KWARANTANNY NA 10 MINUT.")
        
        # 1. Zatrzymaj wszystkie automatyczne mechanizmy
        self.stop_cyclic_check()
        self.cyclic_enabled.set(False)

        # 2. Zablokuj kluczowe przyciski i filtry
        self.search_button.config(state=self._DISABLED)
        self.book_button.config(state=self._DISABLED)
        # Można też zablokować filtry, ale to opcjonalne
        
        # 3. Wyświetl komunikat i uruchom licznik
        end_time = datetime.now() + timedelta(minutes=10)

        def update_quarantine_countdown():
            remaining = end_time - datetime.now()
            if remaining.total_seconds() > 0:
                minutes, seconds = divmod(int(remaining.total_seconds()), 60)
                self.status_var.set(f"BLOKADA API! Koniec za: {minutes:02d}:{seconds:02d}")
                self.root.after(1000, update_quarantine_countdown)
            else:
                self._leave_quarantine()
        
        messagebox.showerror(
            "Aktywność Zablokowana (Błąd 429)",
            "Wykryto aktywność automatu. Możliwość wyszukiwania została tymczasowo zablokowana przez Medicover.\n\nAplikacja wchodzi w 10-minutowy tryb kwarantanny, aby chronić Twoje konto. Wszystkie funkcje zostaną odblokowane automatycznie."
        )
        update_quarantine_countdown()

    def _leave_quarantine(self):
        """Kończy tryb kwarantanny i odblokowuje interfejs."""
        self.is_quarantined = False
        self.logger.info("Koniec kwarantanny. Odblokowuję interfejs.")
        
        # Odblokuj przyciski
        self.search_button.config(state=self._NORMAL)
        self.book_button.config(state=self._NORMAL)
        
        self.status_var.set("Koniec blokady. Można wznowić wyszukiwanie.")

    def toggle_cyclic_check(self):
        """Włącza lub wyłącza cykliczne sprawdzanie."""
        # KROK 1: Zaktualizuj stan panelu auto-rezerwacji na podstawie NOWEJ wartości
        self._update_autobook_widgets_state()

        # KROK 2: Uruchom lub zatrzymaj cykliczne sprawdzanie (stara logika)
        if self.cyclic_enabled.get():
            self.start_cyclic_check()
        else:
            self.stop_cyclic_check()

    def start_cyclic_check(self):
        """Uruchamia cykliczne sprawdzanie wizyt i aktywuje licznik."""
        # Zawsze zatrzymuj poprzednie zadania przed startem nowych
        if self.cyclic_job_id:
            self.root.after_cancel(self.cyclic_job_id)
        if self.countdown_job_id:
            self.root.after_cancel(self.countdown_job_id)

        interval_minutes = self.cyclic_interval.get()
        interval_ms = interval_minutes * 60 * 1000
        
        # Ustaw czas następnego sprawdzenia
        self.next_check_time = datetime.now() + timedelta(minutes=interval_minutes)

        def cyclic_task():
            if self.cyclic_enabled.get():
                self.logger.info("Uruchamianie cyklicznego sprawdzania z filtrami GUI...")
                self.search_appointments_from_gui(is_background_check=True)
                
                # Ustaw czas kolejnego sprawdzenia i zresetuj licznik
                self.next_check_time = datetime.now() + timedelta(minutes=interval_minutes)
                self._update_countdown_label()

                self.cyclic_job_id = self.root.after(interval_ms, cyclic_task)

        # Pierwsze uruchomienie głównego zadania i licznika
        self.cyclic_job_id = self.root.after(interval_ms, cyclic_task)
        self._update_countdown_label() # Uruchom licznik natychmiast
        self.logger.info(f"Cykliczne sprawdzanie uruchomione co {interval_minutes} minut.")


    def stop_cyclic_check(self):
        """Zatrzymuje cykliczne sprawdzanie oraz licznik."""
        if self.cyclic_job_id:
            self.root.after_cancel(self.cyclic_job_id)
            self.cyclic_job_id = None
        
        if self.countdown_job_id:
            self.root.after_cancel(self.countdown_job_id)
            self.countdown_job_id = None

        self.next_check_time = None
        self._update_countdown_label() 
        self.logger.info("Cykliczne sprawdzanie zatrzymane.")

    def update_cyclic_interval(self):
        """
        Aktualizuje interwał, zapisuje go do konfiguracji i restartuje
        cykliczne sprawdzanie, jeśli jest aktywne.
        """
        try:
            new_interval = self.cyclic_interval.get()
            if not 1 <= new_interval <= 120:
                # Opcjonalnie: można dodać messagebox, ale na razie cicha walidacja wystarczy
                self.logger.warning(f"Próba ustawienia nieprawidłowego interwału: {new_interval}")
                return
            
            # Zapisz nową wartość do głównej konfiguracji aplikacji
            self.app.config.data['check_interval_minutes'] = new_interval
            self.app.config.save()
            self.logger.info(f"Zapisano nowy interwał sprawdzania: {new_interval} minut.")

            # Jeśli automatyczne sprawdzanie jest włączone, zrestartuj je z nowym interwałem
            if self.cyclic_enabled.get():
                self.start_cyclic_check()
        except Exception as e:
            self.logger.error(f"Błąd podczas aktualizacji interwału: {e}", exc_info=True)

    # ===================================================================
    # PROFILE MANAGEMENT
    # ===================================================================

    def create_header_panel(self, parent):
        """Tworzy górny panel z tytułem i sekcją zarządzania profilami."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill='x', pady=(0, 10))

        title_label = ttk.Label(header_frame, text="Medicover Appointment Finder", style='Header.TLabel')
        title_label.pack()

        profile_frame = ttk.LabelFrame(header_frame, text="Zarządzanie Profilem", padding=10)
        profile_frame.pack(fill='x', pady=(10, 0))

        ttk.Label(profile_frame, text="Aktywny profil:").grid(row=0, column=0, padx=(0, 5), sticky='w')
        ttk.Label(profile_frame, textvariable=self._profile_var, foreground=self.COLORS['primary'], font=('Segoe UI', 9, 'bold')).grid(row=0, column=1, padx=(0, 20), sticky='w')
        
        ttk.Label(profile_frame, text="Przełącz na:").grid(row=0, column=2, padx=(10, 5), sticky='w')
        self._profile_combobox = ttk.Combobox(profile_frame, state=self._READONLY, width=35)
        self._profile_combobox.grid(row=0, column=3, sticky='ew')
        self._profile_combobox.bind("<<ComboboxSelected>>", self._on_profile_selected)

        ttk.Button(profile_frame, text="Zarządzaj Profilami...", command=self._open_profile_manager).grid(row=0, column=4, padx=(10, 0))
        
        profile_frame.grid_columnconfigure(3, weight=1)

    def _open_profile_manager(self):
        """Otwiera okno menedżera profili."""
        # REF: Użycie zewnętrznej klasy ProfileManagerWindow
        ProfileManagerWindow(self.root, self.app, self._on_profiles_changed)

    def _update_profile_label(self):
        """Aktualizuje etykietę i combobox z aktualnym, sformatowanym profilem."""
        username = self.app.get_current_profile()
        if not username:
            self._profile_var.set("(brak)")
            if hasattr(self, '_profile_combobox'):
                self._profile_combobox.set("")
            return

        profile = self.app.profile_manager.get_profile(username)
        if profile:
            display_name = self._format_profile_display(profile)
            self._profile_var.set(display_name)
            self.profile_header_var.set(f"Zarządzanie Profilem: {display_name}")
            if hasattr(self, '_profile_combobox'):
                self._profile_combobox.set(display_name)

    def _format_profile_display(self, profile):
        """Formatuje obiekt profilu do czytelnego stringa."""
        if profile.description:
            return f"{profile.description} ({profile.username})"
        else:
            return profile.username
    # ===================================================================
    # ACTION METHODS (Refresh, Book, Filter, etc.)
    # ===================================================================

    def search_appointments_from_gui(self, is_background_check: bool = False):
        """
        Uruchamia wyszukiwanie w osobnym wątku. Logika budowania parametrów
        jest wewnątrz wątku, aby zapewnić odczyt najświeższych danych z GUI.
        """
        if self.is_quarantined:
            self.logger.warning("Próba uruchomienia wyszukiwania w trakcie kwarantanny. Blokuję.")
            messagebox.showwarning("Aplikacja Zablokowana", "Aplikacja jest w trybie 10-minutowej kwarantanny. Proszę czekać.")
            return

        if not is_background_check:
            self.status_var.set("Przygotowywanie zapytania do API...")
            self.root.update_idletasks()

        def worker():
            """Wątek roboczy wykonujący całą logikę wyszukiwania."""
            self.logger.info(f"--- Wątek wyszukiwania uruchomiony (tryb tła: {is_background_check}) ---")
            try:
                # Krok 1: Budowanie parametrów zapytania
                search_params = {}
                spec_name = self.filter_specialty.get()
                if not spec_name:
                    self.root.after(0, lambda: messagebox.showerror("Błąd", "Proszę wybrać specjalność."))
                    return
                
                spec_ids = self.app.specialty_manager.get_ids_by_name(spec_name)
                if not spec_ids:
                    self.root.after(0, lambda: messagebox.showerror("Błąd Konfiguracji", f"Brak ID dla specjalności: {spec_name}"))
                    return
                search_params['SpecialtyIds'] = spec_ids

                if selected_doctors := self.doctor_combo.get_checked_items():
                    if doctor_ids := self.app.doctor_manager.get_ids_by_names(selected_doctors):
                        search_params['DoctorIds'] = doctor_ids

                if selected_clinics := self.clinic_combo.get_checked_items():
                    if clinic_ids := self.app.clinic_manager.get_ids_by_names(selected_clinics):
                        search_params['ClinicIds'] = clinic_ids

                date_from_str = self.date_from_entry.get().strip()
                try:
                    datetime.strptime(date_from_str, '%Y-%m-%d')
                    search_params['StartTime'] = date_from_str
                except ValueError:
                    search_params['StartTime'] = datetime.now().strftime('%Y-%m-%d')
                    self.root.after(0, lambda: self.date_from_entry.delete(0, tk.END))
                    self.root.after(0, lambda: self.date_from_entry.insert(0, search_params['StartTime']))

                # Krok 2: Wysłanie zapytania do API
                self.root.after(0, lambda: self.status_var.set("Wyszukiwanie wizyt przez API..."))
                appointments = self.app.search_appointments(search_params)

                if appointments is None:
                    self.root.after(0, self._enter_quarantine)
                    return

                # Krok 3: Filtrowanie po dacie 'do'
                if (date_to_str := self.date_to_entry.get().strip()) and appointments:
                    try:
                        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                        appointments = [apt for apt in appointments if datetime.fromisoformat(apt.get("appointmentDate", "")).date() <= date_to]
                    except (ValueError, TypeError):
                        pass

                # Krok 4: Logika automatycznej rezerwacji
                if is_background_check and self.autobook_enabled.get() and appointments:
                    self.logger.info("Tryb auto-rezerwacji aktywny. Filtrowanie wizyt wg nowych kryteriów...")
                    
                    # Pobierz ustawienia z GUI do zmiennych lokalnych dla wydajności
                    selected_days = {i for i, var in enumerate(self.autobook_days_vars) if var.get()}
                    start_h = self.autobook_start_hour.get()
                    end_h = self.autobook_end_hour.get()

                    for apt in appointments:
                        try:
                            appointment_dt = datetime.fromisoformat(apt.get("appointmentDate", ""))
                            
                            # Test 1: Sprawdź dzień tygodnia (0=Pon, 6=Nd)
                            if appointment_dt.weekday() not in selected_days:
                                continue # Pomiń, jeśli dzień tygodnia się nie zgadza

                            # Test 2: Sprawdź przedział godzinowy
                            appointment_hour = appointment_dt.hour
                            if not (start_h <= appointment_hour <= end_h):
                                continue # Pomiń, jeśli godzina jest poza zakresem

                            # Jeśli wizyta przeszła wszystkie testy, jest kandydatem!
                            self.logger.info(f"Znaleziono pasującą wizytę: {apt.get('appointmentDate')}. Zlecanie rezerwacji.")
                            self.root.after(0, self._perform_autobooking, apt)
                            return # Zakończ wątek po znalezieniu i zleceniu rezerwacji

                        except (ValueError, TypeError):
                            continue # Pomiń wizyty z błędną datą
                
                # Krok 5: Aktualizacja GUI z wynikami
                self.root.after(0, self._update_gui_with_appointments, appointments, "Wyszukiwanie API")

            except LoginRequiredException:
                self.logger.warning("Wymagane ponowne logowanie. Uruchamianie procesu.")
                self.root.after(0, self._execute_login_with_progress_bar, lambda: self.search_appointments_from_gui(is_background_check))
            except Exception as e:
                self.logger.error(f"Krytyczny błąd w wątku wyszukiwania: {e}", exc_info=True)
                self.root.after(0, lambda err=e: self.status_var.set(f"Błąd: {err}"))

        # Uruchomienie wątku
        threading.Thread(target=worker, daemon=True).start()

    def _perform_autobooking(self, appointment: Dict):
        """Wykonuje rezerwację w tle i aktualizuje stan aplikacji."""
        self.logger.info(f"Znaleziono pasującą wizytę. Próba automatycznej rezerwacji...")
        self.status_var.set("Znaleziono wizytę! Próba rezerwacji...")
        
        result = self.app.book_appointment(appointment)
        
        if result.get("success"):
            self.logger.info("Automatyczna rezerwacja zakończona sukcesem!")
            
            # Wyłącz wszystkie automatyczne mechanizmy
            self.stop_cyclic_check()
            self.cyclic_enabled.set(False)
            self.autobook_enabled.set(False)
            self._update_autobook_header()
            doctor = self.extract_doctor_name(appointment)
            date_str, time_str = self.extract_appointment_data(appointment)
            
            self.status_var.set(f"Sukces! Zarezerwowano wizytę {date_str} {time_str}.")
            messagebox.showinfo(
                "Rezerwacja Automatyczna Zakończona",
                f"Pomyślnie zarezerwowano wizytę!\n\nLekarz: {doctor}\nData: {date_str}\nGodzina: {time_str}\n\nAutomatyczne wyszukiwanie i rezerwowanie zostały wyłączone."
            )
            # Odśwież listę, aby pokazać pozostałe wizyty
            self.search_appointments_from_gui()
        else:
            error_msg = result.get("message", "Nieznany błąd.")
            self.logger.error(f"Automatyczna rezerwacja nie powiodła się: {error_msg}")
            self.status_var.set(f"Błąd auto-rezerwacji: {error_msg}")
            # Nie wyłączamy automatyki, spróbujemy ponownie przy następnym cyklu
            
    def _open_calendar(self, entry_widget):
        """Otwiera okno kalendarza i wstawia wybraną datę do podanego widżetu Entry."""
        def on_date_select():
            selected_date = cal.get_date()
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, selected_date)
            top.destroy()

        top = tk.Toplevel(self.root)
        top.withdraw()
        top.transient(self.root)
        top.grab_set()
        
        # Użyjmy importu wewnątrz, aby nie zaśmiecać globalnej przestrzeni nazw
        from tkcalendar import Calendar
        
        try:
            current_date = datetime.strptime(entry_widget.get(), '%Y-%m-%d')
        except ValueError:
            current_date = datetime.now()

        cal = Calendar(top, selectmode='day', year=current_date.year, month=current_date.month, day=current_date.day, date_pattern='y-mm-dd', locale='pl_PL')
        cal.pack(pady=10, padx=10)
        
        ttk.Button(top, text="Wybierz", command=on_date_select).pack(pady=5)

        # Wymuś na Tkinterze, aby przetworzył wszystkie oczekujące zadania
        # i poprawnie obliczył wymiary okna kalendarza.
        top.update_idletasks()

        # Pobierz bezwzględne współrzędne (X, Y) pola Entry na ekranie.
        # Te metody działają poprawnie na wielu monitorach.
        entry_x = entry_widget.winfo_rootx()
        entry_y = entry_widget.winfo_rooty()

        # Oblicz pozycję okna kalendarza, aby pojawiło się tuż pod polem Entry.
        # Dodajemy wysokość pola Entry i mały margines (np. 5 pikseli).
        new_x = entry_x
        new_y = entry_y + entry_widget.winfo_height() + 5

        # Ustaw pozycję okna kalendarza.
        top.geometry(f'+{new_x}+{new_y}')
        top.deiconify()
    def clear_filters(self):
        """Czyści kontrolki filtrów i resetuje widok wyników."""
        self.logger.info("Czyszczenie filtrów i widoku.")
        
        # Resetowanie zmiennych i kontrolek
        self.doctor_combo.uncheck_all()
        self.clinic_combo.uncheck_all()
        available_specialties = self.app.specialty_manager.get_all_names()
        if available_specialties:
            self.filter_specialty.set(available_specialties[0])
        
        self.date_from_entry.delete(0, tk.END)
        self.date_from_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        self.date_to_entry.delete(0, tk.END)

        # Czyszczenie tabeli wyników
        self.appointments = []
        self.filtered_appointments = []
        self.populate_table()
        self.count_var.set("0 wizyt")
        self.status_var.set("Filtry wyczyszczone. Gotowy do nowego wyszukiwania.")

    def book_selected_appointment(self):
        """Rezerwuje wizytę wybraną w tabeli."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Proszę wybrać wizytę do rezerwacji.")
            return

        index = self.tree.index(selection[0])
        if 0 <= index < len(self.filtered_appointments):
            appointment = self.filtered_appointments[index]
            doctor = self.extract_doctor_name(appointment)
            date_str, time_str = self.extract_appointment_data(appointment)

            if messagebox.askyesno("Potwierdzenie rezerwacji", f"Czy na pewno chcesz zarezerwować wizytę?\n\nLekarz: {doctor}\nData: {date_str} o godz. {time_str}"):
                self.perform_booking(appointment)

    def perform_booking(self, appointment: Dict):
        """Wykonuje faktyczną rezerwację wizyty przez API."""
        self.status_var.set("Rezerwowanie wizyty...")
        self.root.update_idletasks()
        try:
            result = self.app.client.book_appointment(appointment)
            if result.get("success"):
                messagebox.showinfo("Sukces", result.get("message", "Wizyta została pomyślnie zarezerwowana."))
                self.status_var.set("Wizyta zarezerwowana.")
                self.search_appointments_from_gui() 
            else:
                error_msg = result.get("message", "Nieznany błąd rezerwacji.")
                messagebox.showerror("Błąd rezerwacji", error_msg)
                self.status_var.set(f"Błąd rezerwacji: {result.get('error', 'nieznany')}")
        except LoginRequiredException:
            self.logger.info("Wykryto potrzebę ponownego logowania przed rezerwacją.")
            # Po zalogowaniu, ponów próbę rezerwacji TEJ SAMEJ wizyty
            self._execute_login_with_progress_bar(lambda: self.perform_booking(appointment))
        except Exception as e:
            self.logger.error(f"Błąd wykonania rezerwacji: {e}", exc_info=True)
            messagebox.showerror("Błąd krytyczny", f"Nie udało się zarezerwować wizyty:\n{e}")
            self.status_var.set("Błąd rezerwacji.")

    def export_appointments(self):
        """Eksportuje przefiltrowane wizyty do pliku tekstowego."""
        if not self.filtered_appointments:
            messagebox.showwarning("Brak danych", "Brak wizyt do wyeksportowania.")
            return

        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            title="Zapisz wizyty do pliku"
        )
        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Lista wizyt Medicover ({datetime.now():%Y-%m-%d %H:%M})\n")
                f.write("=" * 50 + "\n\n")
                for appointment in self.filtered_appointments:
                    details = self.app.client.format_appointment_details(appointment)
                    f.write(details + "\n" + "-" * 30 + "\n\n")
            messagebox.showinfo("Eksport udany", f"Wyeksportowano {len(self.filtered_appointments)} wizyt do pliku.")
            self.status_var.set(f"Wyeksportowano {len(self.filtered_appointments)} wizyt.")
        except Exception as e:
            self.logger.error(f"Błąd eksportu do pliku: {e}", exc_info=True)
            messagebox.showerror("Błąd eksportu", f"Nie udało się zapisać pliku:\n{e}")

    def _sort_by_column(self, event):
        """
        Wywoływana po KAŻDYM lewym kliknięciu w tabelę.
        Sprawdza, czy kliknięto w nagłówek i jeśli tak, sortuje dane.
        """
        # KROK 1: Sprawdź, w który region tabeli kliknięto
        region = self.tree.identify_region(event.x, event.y)

        # Jeśli kliknięcie nie trafiło w nagłówek, natychmiast zakończ funkcję.
        if region != "heading":
            return

        # Od tego momentu mamy pewność, że kliknięto w nagłówek.
        # Reszta logiki pozostaje taka sama.
        column_id = self.tree.identify_column(event.x)
        self.logger.debug(f"--- Sortowanie wywołane dla kolumny: {column_id} ---")

        if column_id not in ['#1', '#2', '#3', '#4', '#5']:
            self.logger.debug("Kliknięto w niesortowalną część nagłówka. Ignorowanie.")
            return

        if column_id == self._sort_column:
            self._sort_direction = not self._sort_direction
        else:
            self._sort_column = column_id
            self._sort_direction = False
        
        self.logger.debug(f"Nowy stan sortowania: kolumna={self._sort_column}, kierunek={'malejąco' if self._sort_direction else 'rosnąco'}")
        
        if not self.filtered_appointments:
            self.logger.debug("Brak danych do sortowania. Zatrzymuję.")
            return

        self.logger.debug(f"Wywoływanie _update_gui_with_appointments z {len(self.filtered_appointments)} elementami.")
        self._update_gui_with_appointments(self.filtered_appointments, source="Sortowanie")
    # ===================================================================
    # DATA EXTRACTION & HELPERS
    # ===================================================================

    def extract_appointment_data(self, appointment: Dict) -> tuple[str, str]:
        """Wyciąga i formatuje datę i godzinę z danych wizyty."""
        datetime_str = appointment.get("appointmentDate", "")
        try:
            dt_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            return dt_obj.strftime("%Y-%m-%d"), dt_obj.strftime("%H:%M")
        except (ValueError, TypeError):
            self.logger.warning(f"Nie udało się sparsować daty: {datetime_str}")
            return "Błędna data", ""

    def extract_doctor_name(self, appointment: Dict) -> str:
        """Wyciąga imię i nazwisko lekarza z danych wizyty."""
        try:
            doctor = appointment.get("doctor", {})
            if isinstance(doctor, dict):
                return doctor.get("name", "Nieznany lekarz").strip()
            return "Nieznany lekarz"
        except Exception:
            return "Nieznany lekarz"

    def extract_specialty_name(self, appointment: Dict) -> str:
        """Wyciąga nazwę specjalności z danych wizyty."""
        try:
            specialty = appointment.get("specialty", {})
            if isinstance(specialty, dict):
                return specialty.get("name", "Nieznana specjalność").strip()
            return "Nieznana specjalność"
        except Exception:
            return "Nieznana specjalność"

    def extract_clinic_name(self, appointment: Dict) -> str:
        """Wyciąga nazwę placówki z danych wizyty."""
        try:
            clinic = appointment.get("clinic", {})
            if isinstance(clinic, dict):
                return clinic.get("name", "Nieznana placówka").strip()
            return "Nieznana placówka"
        except Exception:
            return "Nieznana placówka"
    def _pluralize_visits(self, count: int) -> str:
        """Poprawnie odmienia słowo 'wizyta' w języku polskim."""
        if count == 1:
            return "wizyta"
        # Dla liczb kończących się na 2, 3, 4 (ale nie 12, 13, 14)
        if count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            return "wizyty"
        # Wszystkie inne przypadki (0, 1, 5-21, 25-31 itd.)
        return "wizyt"

def main():
    """Główna funkcja do uruchamiania i testowania GUI."""
    # Dodanie ścieżki do modułów, jeśli skrypt jest uruchamiany bezpośrednio
    # REF: Lepsze jest zainstalowanie pakietu, ale to jest OK dla prostego projektu
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    try:
        from main import MedicoverApp
    except ImportError:
        print("Błąd: Nie można zaimportować 'MedicoverApp' z pliku 'main.py'.")
        print("Upewnij się, że plik 'main.py' znajduje się w tym samym katalogu.")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    app = MedicoverApp()
    gui = MedicoverGUI(app)
    gui.run()


if __name__ == "__main__":
    main()