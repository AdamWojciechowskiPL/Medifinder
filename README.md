# Medicover Appointment Finder

Zaawansowana aplikacja w języku Python do automatycznego wyszukiwania i rezerwowania wizyt lekarskich w systemie Medicover. Aplikacja jest obsługiwana przez w pełni funkcjonalny interfejs graficzny (GUI) i wspiera zarządzanie wieloma profilami użytkowników.

## Kluczowe Funkcjonalności

-   **Intuicyjny Interfejs Graficzny (GUI)**: Aplikacja działa wyłącznie w trybie graficznym (opartym na Tkinter), co zapewnia łatwą i przejrzystą obsługę wszystkich funkcji.
-   **Obsługa Wielu Profili**: Bezpieczne zarządzanie wieloma kontami Medicover. Dane logowania są przechowywane lokalnie, a przełączanie między profilami (np. "Moje konto", "Konto żony") jest proste i szybkie. Opisy profili ułatwiają identyfikację.
-   **Zaawansowane Filtrowanie Wielokrotne**: Możliwość filtrowania wizyt po specjalności oraz **wielu lekarzach i placówkach jednocześnie**, co znacząco zwiększa elastyczność wyszukiwania.
-   **Sortowanie Wyników**: Listę znalezionych wizyt można dynamicznie sortować rosnąco lub malejąco po dowolnej kolumnie (data, lekarz, specjalność, placówka) przez kliknięcie w jej nagłówek.
-   **Automatyczna Rezerwacja (Tryb Bota)**: Eksperymentalna funkcja, która pozwala na automatyczne zarezerwowanie pierwszej wizyty spełniającej kryteria (w tym filtry godzinowe: rano, popołudnie, wieczór). Funkcja jest zabezpieczona komunikatem ostrzegawczym.
-   **Inteligentna Obsługa Blokad API**: Aplikacja wykrywa twarde blokady API (błąd 429) nałożone przez Medicover. W takim przypadku automatycznie wchodzi w 10-minutowy tryb "kwarantanny", blokując interfejs i wyświetlając licznik, aby chronić konto użytkownika.
-   **Zapamiętywanie Stanu Aplikacji**: Po zamknięciu, aplikacja automatycznie zapisuje ostatnio używany profil oraz ustawienia filtrów do pliku `gui_settings.json`, przywracając je przy następnym uruchomieniu.
-   **Niezawodne Logowanie**: Proces logowania przez Selenium jest zoptymalizowany pod kątem omijania podstawowych zabezpieczeń anty-botowych i potrafi inteligentnie czekać na odblokowanie sesji Windows, jeśli aplikacja została uruchomiona na zablokowanym komputerze.

## Architektura Projektu

Aplikacja została zbudowana w oparciu o zasady **modularności** i **separacji odpowiedzialności (SoC)**, co czyni kod czystym i łatwym w utrzymaniu.

-   **`MedicoverApp` (`main.py`)**: Główna klasa aplikacji, która koordynuje pracę wszystkich komponentów.
-   **`MedicoverGUI` (`gui.py`)**: Warstwa prezentacji, odpowiedzialna za wyświetlanie danych i interakcję z użytkownikiem.
-   **`MedicoverClient` (`medicover_client.py`)**: Warstwa logiki biznesowej, zarządzająca sesją i delegująca zadania do niższych warstw.
-   **`MedicoverAuthenticator` (`medicover_authenticator.py`)**: Komponent odpowiedzialny wyłącznie za proces uwierzytelniania przez Selenium.
-   **`Config` (`config.py`) / `ProfileManager`**: Klasy odpowiedzialne za zarządzanie konfiguracją (`credentials.json`) i profilami (`profiles.json`).

## Wymagania Wstępne

-   Python 3.9+
-   Przeglądarka Google Chrome

## Instalacja

1.  **Zainstaluj wymagane biblioteki:**
    Utwórz plik `requirements.txt` (jego zawartość znajduje się poniżej) i uruchom:
    ```bash
    pip install -r requirements.txt
    ```

## Konfiguracja

Przy pierwszym uruchomieniu aplikacja automatycznie utworzy niezbędne pliki konfiguracyjne.

#### 1. `profiles.json`
Ten plik przechowuje dane logowania dla poszczególnych profili. **Przy pierwszym uruchomieniu aplikacja poprosi o stworzenie profilu w menedżerze.** Możesz dodać dowolną liczbę profili.

-   `username`: Twój login do Medicover (e-mail lub numer karty).
-   `password`: Twoje hasło (przechowywane w formie zaszyfrowanej).
-   `description`: Dowolny opis, który będzie widoczny w GUI (np. "Moje konto", "Konto żony").
-   `default`: Ustaw `true` dla jednego profilu, który ma być ładowany domyślnie.

*Przykład:*
```json
[
    {
        "username": "jan.kowalski@email.com",
        "password": "zaszyfrowane_haslo_1",
        "description": "Konto Jana",
        "default": true
    },
    {
        "username": "444555666",
        "password": "zaszyfrowane_haslo_2",
        "description": "Konto Anny",
        "default": false
    }
]
```

#### 2. `credentials.json`
Ten plik przechowuje ogólną konfigurację aplikacji, taką jak domyślny region wyszukiwania czy ustawienia trybu `headless`.

*Przykład:*
```json
{
    "search_params": {
        "region_ids": [
            204
        ]
    },
    "check_interval_minutes": 5,
    "headless": false,
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    }
}
```

#### 3. `gui_settings.json`
Ten plik jest tworzony i zarządzany **automatycznie**. Przechowuje ostatni stan interfejsu użytkownika (wybrany profil, wartości filtrów) i nie powinien być edytowany ręcznie.

## Uruchomienie Aplikacji

Aplikacja działa wyłącznie w trybie graficznym (GUI). Wszystkie opcje, takie jak tryb `headless`, konfiguruje się w pliku `credentials.json`.

#### Uruchomienie Interfejsu Graficznego

To jest jedyny sposób użycia aplikacji. Otwórz terminal w folderze z projektem i uruchom:
```bash
python main.py
```

#### Uruchomienie bez okna konsoli (Windows)

Aby uruchomić aplikację tak, by widoczne było tylko okno GUI (bez czarnego okna konsoli w tle), możesz:
1.  Zmienić nazwę pliku `main.py` na `main.pyw` i uruchamiać go podwójnym kliknięciem.
2.  Uruchomić aplikację komendą:
    ```bash
    pythonw main.py
    ```