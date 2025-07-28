# Medicover Appointment Finder

Zaawansowana aplikacja desktopowa w języku Python do automatycznego wyszukiwania i rezerwowania wizyt lekarskich w systemie Medicover. Aplikacja jest w pełni obsługiwana przez nowoczesny, intuicyjny interfejs graficzny (GUI), wspiera zarządzanie wieloma profilami użytkowników i oferuje spersonalizowane ustawienia dla każdego z nich.

## Kluczowe Funkcjonalności

-   **Nowoczesny Interfejs Graficzny (GUI)**: Aplikacja działa wyłącznie w trybie graficznym (opartym na Tkinter). Interfejs wykorzystuje zwijane sekcje ("akordeon"), aby zmaksymalizować przestrzeń dla najważniejszego elementu – listy znalezionych wizyt.
-   **Zarządzanie Wieloma Profilami**: Bezpieczne zarządzanie wieloma kontami Medicover (np. dla całej rodziny). Dane logowania są szyfrowane i przechowywane lokalnie, a przełączanie między profilami jest proste i szybkie.
-   **Ustawienia Per Profil**: Każdy profil użytkownika ma swoje własne, unikalne ustawienia filtrów i automatyzacji, które są automatycznie zapisywane i wczytywane przy przełączaniu.
-   **Zaawansowane Filtrowanie Wielokrotne**: Możliwość filtrowania wizyt po specjalności oraz **wielu lekarzach i placówkach jednocześnie**, co znacząco zwiększa elastyczność wyszukiwania.
-   **Sortowanie Wyników**: Listę znalezionych wizyt można dynamicznie sortować rosnąco lub malejąco po dowolnej kolumnie (data, lekarz, specjalność, placówka) przez kliknięcie w jej nagłówek.
-   **Elastyczna Automatyczna Rezerwacja (Tryb Bota)**: Funkcja, która pozwala na automatyczne zarezerwowanie pierwszej wizyty spełniającej szczegółowe kryteria, takie jak **wybrane dni tygodnia** oraz **dokładny przedział godzinowy** (np. od 10:00 do 15:00).
-   **Inteligentna Obsługa Blokad API**: Aplikacja wykrywa twarde blokady API (błąd 429) nałożone przez Medicover. W takim przypadku automatycznie wchodzi w 10-minutowy tryb "kwarantanny", blokując interfejs i wyświetlając licznik, aby chronić konto użytkownika.
-   **Niezawodne Logowanie**: Proces logowania przez Selenium jest zoptymalizowany pod kątem omijania podstawowych zabezpieczeń anty-botowych i potrafi inteligentnie czekać na odblokowanie sesji Windows.

## Architektura Projektu

Aplikacja została zbudowana w oparciu o zasady **modularności** i **separacji odpowiedzialności (SoC)**, z wyraźnym podziałem na kod aplikacji i pliki konfiguracyjne.

```
medicover-app/
│
├── config/                # Katalog na wszystkie pliki konfiguracyjne
│   ├── credentials.json
│   ├── profiles.json
│   └── ...
│
├── app/                   # Katalog z kodem źródłowym aplikacji
│   ├── main.py
│   ├── gui.py
│   └── ...
│
├── requirements.txt       # Lista zależności Pythona
├── install.bat            # Skrypt instalacyjny
├── run.py                 # Główny plik startowy aplikacji
└── start.bat              # Skrypt uruchomieniowy dla użytkownika
```

## Wymagania Wstępne

-   Windows 10 lub nowszy
-   Python 3.9+
-   Przeglądarka Google Chrome

## Instalacja

Proces instalacji jest w pełni zautomatyzowany.

1.  **Pobierz i zainstaluj Pythona**: Jeśli nie masz go na komputerze, pobierz instalator ze strony `python.org`. **Ważne:** Podczas instalacji zaznacz opcję **"Add Python to PATH"**.

2.  **Rozpakuj archiwum z aplikacją** do wybranego folderu.

3.  **Uruchom instalator**: Kliknij dwukrotnie plik **`install.bat`**. Skrypt automatycznie:
    *   Sprawdzi, czy Python jest dostępny.
    *   Stworzy izolowane środowisko wirtualne w folderze `venv/`.
    *   Zainstaluje wszystkie wymagane biblioteki.
    Postępuj zgodnie z instrukcjami w oknie konsoli.

## Uruchomienie Aplikacji

Po pomyślnej instalacji, aplikację uruchamia się w bardzo prosty sposób:

**Kliknij dwukrotnie plik `start.bat`**.

Pojawi się wyłącznie okno aplikacji, bez dodatkowego okna konsoli w tle.

## Pierwsze Użycie i Konfiguracja

Przy pierwszym uruchomieniu aplikacja automatycznie utworzy niezbędne pliki w katalogu `config/`.

#### 1. Tworzenie Profilu
Aplikacja poprosi Cię o stworzenie pierwszego profilu. Przejdź do zwijanej sekcji **"Zarządzanie Profilem"** i użyj przycisku **"Zarządzaj Profilami..."**. Będziesz musiał podać:
-   **Login**: Twój numer karty Medicover.
-   **Hasło**: Twoje hasło do systemu Medicover.
-   **Twoja nazwa konta**: Dowolna, czytelna nazwa, która będzie widoczna w GUI (np. "Moje konto", "Konto Adama").

#### 2. Pliki Konfiguracyjne
Wszystkie pliki konfiguracyjne znajdują się w folderze `config/`:
-   `profiles.json`: Przechowuje Twoje profile użytkowników. Hasła są w nim **zaszyfrowane**.
-   `profile_key.key`: **Klucz do szyfrowania haseł**. Jest on unikalny dla Twojego komputera. **Ważne:** Jeśli chcesz przenieść aplikację na inny komputer, musisz skopiować zarówno `profiles.json`, jak i ten plik klucza.
-   `gui_settings.json`: Plik zarządzany **automatycznie**. Przechowuje ostatni stan interfejsu (filtry, ustawienia automatyzacji) dla każdego profilu.
-   `credentials.json`: Przechowuje ogólną konfigurację aplikacji, taką jak domyślny region wyszukiwania czy ustawienia trybu `headless`.
