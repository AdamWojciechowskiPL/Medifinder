# run.py
import sys
from pathlib import Path

# Definiujemy absolutne ścieżki, które będą działać wszędzie
ROOT_DIR = Path(__file__).parent.resolve()
APP_DIR = ROOT_DIR / "app"
CONFIG_DIR = ROOT_DIR / "config"

# Dodajemy katalog 'app' do ścieżki Pythona, aby mógł znaleźć moduły
sys.path.insert(0, str(APP_DIR))

# Teraz, gdy ścieżka jest ustawiona, możemy bezpiecznie importować
from main import MedicoverApp
from gui import MedicoverGUI

def start_application():
    """
    Główna funkcja, która inicjalizuje i uruchamia aplikację,
    przekazując do niej ścieżkę do katalogu z konfiguracją.
    """
    try:
        # Przekazujemy ścieżkę do konfiguracji do głównej klasy aplikacji
        app = MedicoverApp(CONFIG_DIR)

        print("🚀 Uruchamianie interfejsu graficznego...")
        gui = MedicoverGUI(app, CONFIG_DIR)
        gui.run()

    except KeyboardInterrupt:
        print("\n🛑 Działanie przerwane przez użytkownika.")
    except Exception as e:
        # Ta obsługa błędów jest kluczowa, jeśli coś pójdzie nie tak na starcie
        import logging
        logging.basicConfig()
        logging.getLogger(__name__).critical(f"Wystąpił błąd krytyczny podczas uruchamiania: {e}", exc_info=True)
        print(f"❌ Błąd krytyczny: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_application()