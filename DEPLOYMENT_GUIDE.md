# 🚀 Medifinder - Przewodnik Wdrażania na Railway

## Spis Treści
1. [Wymagania Wstępne](#wymagania-wstępne)
2. [Konfiguracja Railway](#konfiguracja-railway)
3. [Deployment](#deployment)
4. [Konfiguracja Zmiennych Środowiskowych](#konfiguracja-zmiennych-środowiskowych)
5. [Testowanie](#testowanie)
6. [Rozwiązywanie Problemów](#rozwiązywanie-problemów)

## Wymagania Wstępne

- Konto na [railway.app](https://railway.app) (rejestracja przez GitHub)
- Git zainstalowany na komputerze
- Token dostępu do GitHub

## Konfiguracja Railway

### Krok 1: Przygotowanie Repozytorium

```bash
# Sklonuj repozytorium
git clone https://github.com/AdamWojciechowskiPL/Medifinder.git
cd Medifinder

# Przejdź na gałąź deploymentu
git checkout railway-deployment
```

### Krok 2: Zalogowanie do Railway

```bash
# Zainstaluj Railway CLI
npm i -g @railway/cli

# Zaloguj się
railway login
```

### Krok 3: Inicjalizacja Projektu Railway

```bash
# W katalogu głównym projektu
railway init

# Wybierz nazwę projektu: "Medifinder"
# Potwierdź konfigurację
```

## Deployment

### Opcja 1: Deployment przez Railway CLI (Rekomendowane)

```bash
# Usuń katalog .git jeśli chcesz fresza
rm -rf .git

# Zainicjuj nowe repozytorium
git init
git add .
git commit -m "Initial Medifinder deployment setup"

# Wdróż na Railway
railway up
```

### Opcja 2: Deployment przez GitHub (Automatyczny)

1. Wejdź na [dashboard.railway.app](https://dashboard.railway.app)
2. Kliknij **"New Project"** → **"Deploy from GitHub"**
3. Połącz swoje repozytorium GitHub
4. Wybierz gałąź `railway-deployment`
5. Railway automatycznie uruchomi deployment

## Konfiguracja Zmiennych Środowiskowych

Wejdź do ustawień projektu w Railway i dodaj poniższe zmienne:

```env
# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=False

# Server Configuration
PORT=5000

# Application Configuration
DEBUG=False
LOG_LEVEL=INFO

# Chrome Configuration
CHROME_BIN=/usr/bin/chromium-browser
CHROMEDRIVER_PATH=/usr/bin/chromedriver

# API Configuration
CORS_ORIGINS=*

# Profile Management
PROFILE_ENCRYPTION_ENABLED=True
PROFILE_KEY_FILE=config/profile_key.key

# Medicover API
MEDICOVER_API_TIMEOUT=30
MEDICOVER_MAX_RETRIES=3
MEDICOVER_HEADLESS_MODE=True
```

## Testowanie

### Sprawdzenie Statusu Wdrażania

```bash
# Sprawdź logi w Railway
railway logs

# Lub przez dashboard Railway
```

### Testowanie API

```bash
# Health check
curl https://[YOUR_RAILWAY_URL]/health

# Pobierz profile
curl https://[YOUR_RAILWAY_URL]/api/v1/profiles

# Wyszukaj wizyty (POST request)
curl -X POST https://[YOUR_RAILWAY_URL]/api/v1/appointments/search \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "your-profile-id",
    "specialty": "Kardiologia",
    "doctors": [],
    "clinics": [],
    "preferred_days": [1,2,3,4,5],
    "time_range": {"start": "08:00", "end": "20:00"}
  }'
```

## Struktura Projektu

```
Medifinder/
├── backend/
│   ├── app/                    # Oryginalny kod aplikacji
│   │   ├── main.py            # MedicoverApp
│   │   ├── gui.py             # MedicoverGUI
│   │   └── ...
│   ├── config/                 # Konfiguracja i dane
│   │   ├── profiles.json
│   │   └── credentials.json
│   ├── main.py                 # Flask API
│   ├── requirements.txt        # Zależności Pythona
│   ├── Dockerfile              # Konfiguracja Docker
│   └── .env.example            # Przykład zmiennych
├── frontend/
│   ├── index.html              # Interfejs HTML
│   ├── style.css               # Style CSS
│   └── script.js               # Logika JavaScript
├── railway.toml                # Konfiguracja Railway
├── DEPLOYMENT_GUIDE.md         # Ten plik
└── README.md                   # Główna dokumentacja
```

## Czym się różni Railway od konkurencji?

| Cecha | Railway | Render | Heroku |
|-------|---------|--------|--------|
| **Darmowy kredyt** | $5/mies | $5.00 trial | Brak |
| **Spin-down** | Nie | Po 15 min | N/A |
| **Support Chrome** | ✅ | ✅ | ✅ |
| **Uptime** | 99.9% | 99% | 99.95% |
| **Limitacja** | Brak po kredycie | Tak | N/A |
| **Skalowanie** | Elastyczne | Ograniczone | N/A |

## Rozwiązywanie Problemów

### Problem: "Chrome nie znaleziony"

**Rozwiązanie:** Dockerfile ma zainstalowany chromium-browser. Jeśli problem się powtarza:

```dockerfile
# Dodaj do Dockerfile:
RUN apt-get install -y chromium-browser chromium-driver
```

### Problem: "Port w użyciu"

**Rozwiązanie:** Railway automatycznie przypisuje PORT. Upewnij się, że backend nasluchuje na `0.0.0.0:$PORT`

### Problem: "Timeout wyszukiwania"

**Rozwiązanie:** Zwiększ timeout w `main.py`:

```python
@app.route('/api/v1/appointments/search', methods=['POST'])
def search_appointments():
    # Zwiększ limit czasowy na 120 sekund
    ...
```

### Problem: "CORS Error w Frontend"

**Rozwiązanie:** Zmienne env zostały ustawione. Sprawdź:

```python
CORS(app)  # W main.py
CORS_ORIGINS=*  # W zmiennych Railway
```

## Zaawansowana Konfiguracja

### Skalowanie Zasobów

W dashboard Railway → Project Settings → Resources:

```yaml
CPU: shared-cpu (darmowe)
RAM: 512MB (minimum dla Selenium + Chrome)
Dysk: Do dyspozycji
```

### Persistentne Storage

Dodaj storage w Railway dla zachowania danych:

```yaml
MountPath: /app/config
Size: 1GB
```

## Monitorowanie

### Logi Aplikacji

```bash
railway logs --follow
```

### Metryki Systemu

Otwórz dashboard Railway → Metrics:
- CPU Usage
- Memory Usage
- Network I/O
- Deploy History

## Aktualizacje i Utrzymanie

### Wdrażanie Aktualizacji

```bash
# Zacommituj zmiany
git add .
git commit -m "Update: [opis zmian]"

# Push uruchomi automatyczny deployment
git push origin railway-deployment
```

### Rollback

W dashboard Railway:
1. Przejdź do "Deployments"
2. Kliknij na poprzednią wersję
3. Kliknij "Redeploy"

## Wsparcie i Dokumentacja

- [Railway Docs](https://docs.railway.app)
- [Flask Documentation](https://flask.palletsprojects.com)
- [Selenium Documentation](https://selenium.dev/documentation)
- [GitHub Medifinder](https://github.com/AdamWojciechowskiPL/Medifinder)

## Bezpieczeństwo

⚠️ **WAŻNE:**

1. **Nie commituj sekretów!** Używaj `.env` i Railway variables
2. **Haseł nigdy nie przechowuj jako plaintext**
3. **Szyfruj dane wrażliwe** (już implementowane w aplikacji)
4. **Regularne backupy** konfiguracji i profili

## Licencja

MIT - Patrz LICENSE

## Autor

AdamWojciechowskiPL

---

**Powodzenia z wdrażaniem Medifinder na Railway! 🚀**
