# START OF FILE: custom_widgets.py (Wersja z niezawodnym zamykaniem "grab")
import tkinter as tk
from tkinter import ttk

class ChecklistCombobox(ttk.Frame):
    """
    Niestandardowy widżet, który wygląda jak Combobox,
    ale po kliknięciu rozwija listę z polami wyboru (checkboxami).
    Wersja z niezawodnym zamykaniem opartym na mechanizmie 'grab'.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._items = []
        self._checked_vars = {}

        self._button = ttk.Button(self, text="Wybierz...", command=self._toggle_dropdown)
        self._button.pack(fill=tk.BOTH, expand=True)

        self._dropdown = tk.Toplevel(self)
        self._dropdown.withdraw()
        self._dropdown.transient(self.winfo_toplevel())
        self._dropdown.overrideredirect(True)

        self._action_frame = ttk.Frame(self._dropdown)
        self._action_frame.pack(side="top", fill="x", pady=3, padx=3)
        style = ttk.Style()
        style.configure("Action.TButton", padding=3)
        ttk.Button(self._action_frame, text="Wszystkie", command=self.select_all, style="Action.TButton").pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(self._action_frame, text="Żadne", command=self.uncheck_all, style="Action.TButton").pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(self._action_frame, text="Zamknij", command=self._hide_dropdown, style="Action.TButton").pack(side="left", expand=True, fill="x", padx=1)

        self._list_frame = ttk.Frame(self._dropdown, relief="solid", borderwidth=1)
        self._list_frame.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(self._list_frame, borderwidth=0, highlightthickness=0)
        self._canvas.bind('<Enter>', self._bind_mousewheel)
        self._canvas.bind('<Leave>', self._unbind_mousewheel)
        self._checkbox_frame = ttk.Frame(self._canvas)
        self._scrollbar = ttk.Scrollbar(self._list_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.create_window((0, 0), window=self._checkbox_frame, anchor="nw")
        
        self._checkbox_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

    def _toggle_dropdown(self):
        """Pokazuje lub ukrywa listę wyboru w zależności od jej stanu."""
        if self._dropdown.winfo_viewable():
            self._hide_dropdown()
        else:
            self._show_dropdown()

    def _on_grab_click(self, event):
        """
        Przechwytuje wszystkie kliknięcia, gdy lista jest otwarta.
        Zamyka listę, jeśli kliknięcie nastąpiło poza jej granicami.
        """
        x, y, width, height = self._dropdown.winfo_rootx(), self._dropdown.winfo_rooty(), self._dropdown.winfo_width(), self._dropdown.winfo_height()
        
        if not (x < event.x_root < x + width and y < event.y_root < y + height):
            self._hide_dropdown()

    def _show_dropdown(self):
        """Pokazuje listę i ustawia globalny 'grab' na mysz."""
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        width = self.winfo_width()
        self._dropdown.geometry(f"{width}x250+{x}+{y}")
        self._dropdown.deiconify()
        self._dropdown.lift()
        
        self._dropdown.grab_set()
        self._dropdown.bind("<Button-1>", self._on_grab_click)

    def _hide_dropdown(self):
        """Ukrywa listę i, co najważniejsze, zwalnia 'grab'."""
        self._dropdown.grab_release()
        
        # Reszta logiki pozostaje bez zmian
        self.focus_set()
        self._dropdown.withdraw()
        self._update_text()

    def set_items(self, items: list[str]):
        """Ustawia listę dostępnych opcji do wyboru."""
        checked_before = self.get_checked_items()
        
        for widget in self._checkbox_frame.winfo_children():
            widget.destroy()
        
        self._items = items
        self._checked_vars = {item: tk.BooleanVar() for item in items}

        for item in self._items:
            cb = ttk.Checkbutton(self._checkbox_frame, text=item, variable=self._checked_vars[item])
            cb.pack(anchor="w", fill="x", padx=5, pady=2)
        
        self.set_checked_items(checked_before)

    def get_checked_items(self) -> list[str]:
        """Zwraca listę zaznaczonych opcji."""
        return [item for item, var in self._checked_vars.items() if var.get()]

    def set_checked_items(self, items_to_check: list[str]):
        """Ustawia, które opcje mają być zaznaczone."""
        for item, var in self._checked_vars.items():
            var.set(item in items_to_check)
        self._update_text()

    def select_all(self):
        """Zaznacza wszystkie dostępne opcje."""
        for var in self._checked_vars.values():
            var.set(True)
        self._update_text()

    def uncheck_all(self):
        """Odznacza wszystkie opcje."""
        for var in self._checked_vars.values():
            var.set(False)
        self._update_text()

    def _update_text(self):
        """Aktualizuje tekst na głównym przycisku."""
        checked_items = self.get_checked_items()
        if not checked_items:
            self._button.config(text="Wybierz...")
        elif len(checked_items) == 1:
            self._button.config(text=checked_items[0])
        else:
            self._button.config(text=f"{len(checked_items)} zaznaczonych")
    def _on_mousewheel(self, event):
        """Obsługuje przewijanie kółkiem myszy na płótnie."""
        # Dzielenie przez 120 normalizuje prędkość przewijania w systemie Windows
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
    def _bind_mousewheel(self, event):
        """Włącza nasłuchiwanie na zdarzenie kółka myszy."""
        # Używamy bind_all, aby przechwycić zdarzenie nawet na widżetach potomnych (checkboxach)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """Wyłącza nasłuchiwanie na zdarzenie kółka myszy."""
        self._canvas.unbind_all("<MouseWheel>")
# END OF FILE: custom_widgets.py