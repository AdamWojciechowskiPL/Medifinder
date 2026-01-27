# 🏥 Medifinder - Platforma Webowa

Zaawansowana platforma webowa do automatycznego wyszukiwania i rezerwacji wizyt w systemie Medicover.
Zaprojektowana do działania w chmurze (Railway.app), oferuje dostęp 24/7, automatyczne harmonogramy i obsługę wielu profili.

## 🌟 Główne Funkcje

*   **Webowy Interfejs**: Responsywny frontend (HTML/JS) dostępny z dowolnego urządzenia.
*   **Automatyzacja (Scheduler)**: Wbudowany harmonogram sprawdzania wizyt w tle (nawet gdy przeglądarka jest zamknięta).
*   **Wieloprofilowość**: Obsługa wielu kont Medicover (rodzina/znajomi) z izolacją sesji.
*   **Inteligentne Filtrowanie**: Wyszukiwanie po specjalnościach, konkretnych lekarzach, placówkach i przedziałach godzinowych.
*   **Szyfrowanie**: Hasła przechowywane lokalnie (AES-256), nie wysyłane do zewnętrznych serwerów (poza Medicover).
*   **Smart Session Management**: Automatyczne przedłużanie sesji przy każdym żądaniu API (uniknięcie nadmiarowych logowań).
*   **Cloud Native**: Zoptymalizowana pod konteneryzację (Docker) i wdrożenie na Railway.app.

## 🏛️ Architektura

Aplikacja działa jako pojedynczy serwis (Monolit) w kontenerze Docker:
*   **Backend**: Python 3.11 + Flask (REST API).
*   **Core**: Selenium WebDriver (Headless Chrome) do interakcji z Medicover.
*   **Session Management**: Bearer token z 5-minutowym TTL, automatycznie odświeżanym przy użyciu.
*   **Task Queue**: Wewnętrzny APScheduler do zadań w tle (nie blokuje API).
*   **Frontend**: Statyczne pliki HTML/JS serwowane bezpośrednio przez Flask.
*   **Storage**: Wolumeny dyskowe do trwałego zapisu konfiguracji (`/config`).

### ♻️ Zarządzanie Sesjami (Bearer Tokens)

Aplikacja implementuje inteligentny system cache sesji:

*   **TTL (Time To Live)**: Każdy bearer token ma 5-minutowy czas ważności.
*   **Automatyczne Odświeżanie**: Przy każdym udanym użyciu tokenu (search/book) TTL jest automatycznie przedłużane o kolejne 5 minut.
*   **Lazy Authentication**: Jeśli token wygasł, system automatycznie wykonuje relogowanie w tle bez przerywania operacji użytkownika.
*   **Izolacja Sesji**: Każdy profil ma własną, niezależną sesję z oddzielną ścieżką wygasania.

**Korzyści:**
- Minimalizacja użycia Selenium (logowanie tylko gdy konieczne)
- Szybsze odpowiedzi API (brak opóźnień związanych z przegladarką)
- Lepsza stabilność dla schedulerów (długie zadania wykorzystują tę samą sesję)

## 🚀 Wdrożenie (Railway)

Aplikacja jest skonfigurowana do natychmiastowego wdrożenia na Railway.app.

1.  Zforkuj to repozytorium.
2.  Zaloguj się do [Railway.app](https://railway.app).
3.  Utwórz nowy projekt -> "Deploy from GitHub repo".
4.  Wybierz to repozytorium.
5.  Railway automatycznie wykryje `Dockerfile` i `railway.toml`.

**Zmienne środowiskowe (opcjonalne):**
*   `FLASK_SECRET_KEY`: Losowy ciąg znaków dla sesji.
*   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Do logowania przez Google (jeśli używane).

## 💻 Uruchomienie Lokalne

Wymagany Python 3.11+ oraz Google Chrome.

1.  Sklonuj repozytorium:
    ```bash
    git clone https://github.com/AdamWojciechowskiPL/Medifinder.git
    cd Medifinder
    ```
2.  Zainstaluj zależności:
    ```bash
    pip install -r requirements.txt
    ```
3.  Uruchom serwer:
    ```bash
    python run.py
    ```
4.  Otwórz `http://localhost:5000`.

## 📚 API Endpoints

### Auth & System
*   `GET /health` - Status usługi.
*   `POST /auth/login` - Logowanie (OAuth/Session).

### Profile & Słowniki
*   `GET /api/v1/profiles` - Lista dostępnych profili.
*   `POST /api/v1/profiles/add` - Dodawanie zaszyfrowanego profilu.
*   `GET /api/v1/dictionaries/{specialties|doctors|clinics}` - Dane słownikowe.

### Wizyty & Scheduler
*   `POST /api/v1/appointments/search` - Jednorazowe wyszukiwanie.
*   `POST /api/v1/appointments/book` - Rezerwacja wizyty.
*   `POST /api/v1/scheduler/start` - Uruchomienie cyklicznego szukania.
*   `GET /api/v1/scheduler/results` - Pobranie wyników z tła.

## 🔒 Bezpieczeństwo

*   Hasła do profili Medicover są szyfrowane kluczem AES-256 generowanym przy pierwszym uruchomieniu (`config/profile_key.key`).
*   Komunikacja z Medicover odbywa się przez izolowaną sesję przeglądarki.
*   Bearer tokens są przechowywane w pamięci (nie na dysku) z automatycznym wygasaniem.
*   Żadne dane medyczne nie są przesyłane do twórców aplikacji.

---
*Autor: AdamWojciechowskiPL*
