# 🟥 Medifinder - Wersja Webowa

**Automatyczne wyszukiwanie i rezerwacja wizyt lekarskich Medicover - teraz dostępne jako aplikacja webowa!**

## 🌟 Cechy Główne

✅ **Nowoczesny Interfejs Webowy** - Responsywny design, działa na wszystkich urządzeniach
✅ **Zarządzanie Wieloma Profilami** - Obsługa całej rodziny
✅ **Zaawansowane Filtrowanie** - Specjalność, lekarz, placówka, godziny
✅ **Automatyczna Rezerwacja** - Tryb bota z inteligentnym planiowaniem
✅ **Bezpieczeństwo** - Szyfrowanie haseł lokalnie
✅ **Dostępna na Chmurze** - Wdrażanie na Railway.app - zawsze dostępna
✅ **Bez Instalacji** - Wystarczy przeglądarka internetowa

## 💻 Technologia Stack

### Backend
- **Python 3.11** z Flask REST API
- **Selenium 4** z Chrome WebDriver
- **Cryptography** do szyfrowania haseł
- **Docker** dla spójnego środowiska

### Frontend
- **HTML5** - Semantyczna struktura
- **CSS3** - Modern responsive design
- **JavaScript (Vanilla)** - Zero dependencji

### Deployment
- **Railway.app** - Cloud hosting ($5/miesiąc kredytu)
- **Docker** - Containerization
- **GitHub** - Version control i CI/CD

## 🚀 Quick Start

### Wymagania
- Konto na Railway.app (rejestracja przez GitHub)
- Git zainstalowany
- Przeglądarka internetowa (dowolna)

### 1. Deployment (2 minuty)

```bash
# Klonuj repozytorium
git clone https://github.com/AdamWojciechowskiPL/Medifinder.git
cd Medifinder
git checkout railway-deployment

# Zaloguj się do Railway
railway login

# Wdrażanie
railway up
```

### 2. Otwarcie Aplikacji

Po wdrażaniu:
1. Otwórz link dostarczony przez Railway (np. `https://medifinder-xyz.railway.app`)
2. Dodaj swój profil Medicover
3. Skonfiguruj parametry wyszukiwania
4. Zacznij szukać wizyt!

## 📱 Jak Używać?

### Dodawanie Profilu

1. Przejdź do karty **"Profil"**
2. Kliknij **"+ Dodaj Nowy Profil"**
3. Wprowadź:
   - **Nazwa**: Twoja nazwa (np. "Moje konto")
   - **Login**: Numer karty Medicover
   - **Hasło**: Hasło do Medicover
4. Kliknij **"Dodaj Profil"**

### Wyszukiwanie Wizyt

1. Przejdź do karty **"Wyszukaj"**
2. Wypełnij formularz:
   - **Profil**: Wybierz profil
   - **Specjalność**: np. "Kardiologia"
   - **Lekarze** (opcjonalnie): np. "Dr. Smith, Dr. Johnson"
   - **Placówki** (opcjonalnie): np. "Warszawa"
   - **Preferowane dni**: Zaznacz dni
   - **Godziny**: Ustaw przedział czasowy
3. Opcjonalnie zaznacz **"Automatyczna rezerwacja"**
4. Kliknij **"Szukaj Wizyt"**
5. Wyniki pojawią się w karcie **"Wyniki"**

### Rezerwacja Wizyty

1. W karcie "Wyniki" kliknij **"Zarezerwuj"** przy wybranej wizycie
2. Wizyta zostanie zarezerwowana automatycznie
3. Potwierdzenie pojawi się w powiadomieniu

### Tryb Automatyczny

Zaznacz "🤖 Automatyczna rezerwacja" aby:
- Aplikacja automatycznie rezerwowała pierwszą dostępną wizytę
- Oszczędzać czas na ręczne wyszukiwanie
- Przechwytywać wizyty natychmiast po ich pojawieniu się

## 🔐 Bezpieczeństwo

✅ **Szyfrowanie Haseł** - AES-256 encryption
✅ **HTTPS** - Całość komunikacji szyfrowana
✅ **Brak Przechowywania Haseł** - Tylko dla aktualnej sesji
✅ **Izolacja Danych** - Każdy użytkownik ma własny profil
✅ **Regularne Aktualizacje** - Automatyczne patche bezpieczeństwa

## 📊 Architektura Aplikacji

```
Przegląd → Frontend (HTML/CSS/JS)
            ↓
           API (Flask REST)
            ↓
         Backend (Python)
            ↓
       Selenium/ChromeDriver
            ↓
        Medicover Website
```

## 🛠️ API Endpoints

### Profili
```
GET  /api/v1/profiles              - Pobierz listę profili
POST /api/v1/profiles/add          - Dodaj nowy profil
```

### Wizyty
```
POST /api/v1/appointments/search   - Wyszukaj wizyty
POST /api/v1/appointments/book     - Zarezerwuj wizytę
POST /api/v1/appointments/auto-book - Automatyczna rezerwacja
```

### System
```
GET  /health                        - Health check
```

## 📈 Monitorowanie

W Railway Dashboard możesz obserwować:
- **CPU Usage** - Zużycie procesora
- **Memory Usage** - Pamięć operacyjna
- **Network I/O** - Przychodzące/wychodzące dane
- **Deployment History** - Historia wdrożeń
- **Logi** - Szczegółowe logi aplikacji

## ⚙️ Konfiguracja Railway

Zmienne środowiskowe w Railway Dashboard:

```env
FLASK_ENV=production
DEBUG=False
LOG_LEVEL=INFO
CORS_ORIGINS=*
MEDICOVER_HEADLESS_MODE=True
```

## 🐛 Rozwiązywanie Problemów

### Problem: "Nie mogę się zalogować"
**Rozwiązanie**: Upewnij się, że:
- Login to numer karty Medicover (12 cyfr)
- Hasło jest prawidłowe
- Konto nie jest zablokowane w Medicover

### Problem: "Wyszukiwanie nie zwraca wyników"
**Rozwiązanie**:
- Sprawdź czy specjalność jest wpisana prawidłowo
- Spróbuj innego przedziału godzinowego
- Wśród wybranych dni mogą nie być dostępne wizyty

### Problem: "Aplikacja działa powoli"
**Rozwiązanie**:
- Railway może ograniczać resources
- Spróbuj zmniejszyć liczbę filtrów
- Oczekiwane slowdown przy pierwszym wyszukiwaniu (~30 sek)

### Problem: "Port w użyciu"
**Rozwiązanie**: Railway automatycznie przypisuje PORT - nie musisz się tym martwić

## 📚 Dokumentacja

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Szczegółowy przewodnik wdrożenia
- [README.md](README.md) - Dokumentacja wersji desktopowej
- [API Documentation](#api-endpoints) - Specyfikacja API

## 📦 Struktura Projektu

```
Medifinder/
├── backend/
│   ├── app/                 # Oryginalny kod aplikacji
│   ├── config/              # Konfiguracja i dane
│   ├── main.py              # Flask API
│   ├── requirements.txt      # Zależności Python
│   ├── Dockerfile           # Docker configuration
│   └── .env.example
├── frontend/
│   ├── index.html           # Interfejs HTML
│   ├── style.css            # Style CSS
│   └── script.js            # Logika JavaScript
├── railway.toml             # Railway deployment config
├── DEPLOYMENT_GUIDE.md      # Przewodnik wdrażania
└── README_WEB.md            # Ten plik
```

## 🤝 Wkład

Masz sugestię lub znalazłeś bug?
1. Otwórz Issue na GitHub
2. Wyjaśnij problem/sugestię
3. Przeslij Pull Request z poprawką

## 📜 Licencja

MIT - Patrz plik LICENSE

## 👤 Autor

AdamWojciechowskiPL

## 🙏 Podziękowania

- [Railway.app](https://railway.app) - Hosting
- [Selenium](https://selenium.dev) - Web Automation
- [Flask](https://flask.palletsprojects.com) - Web Framework
- GitHub Community - Support

---

**Gotowy do wdrożenia? 🚀 Przejdź do [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**

**Potrzebujesz pomocy? 💬 Otwórz issue na GitHub**

---

*Medifinder - Sprawdzanie wizyt lekarskich nigdy nie było takie proste!*
❤️
