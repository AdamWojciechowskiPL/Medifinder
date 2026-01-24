# 🚀 Medifinder - Railway Deployment Quick Start

## W 5 Minut do Chmury!

### Krok 1: Przygotowanie (1 minuta)

```bash
# Zaloguj się do Railway (jeśli jeszcze tego nie zrobiłeś)
# https://railway.app - Zarejestruj się przez GitHub

# Zainstaluj Railway CLI
npm install -g @railway/cli

# Zaloguj się
railway login
```

### Krok 2: Wdrożenie (2 minuty)

```bash
# Sklonuj repo
git clone https://github.com/AdamWojciechowskiPL/Medifinder.git
cd Medifinder

# Przejdź na gałąź deployment
git checkout railway-deployment

# Wdróż!
railway up
```

### Krok 3: Uruchom! (2 minuty)

1. Railway poda Ci URL aplikacji (np. `https://medifinder-xyz.railway.app`)
2. Otwórz URL w przeglądarce
3. **Gotowe!** 🎉

---

## Pierwsza Konfiguracja

### W Aplikacji:

1. **Przejdź do karty "Profil"**
2. **Kliknij "Dodaj Nowy Profil"**
3. **Wypełnij dane:**
   - Nazwa: Jakakolwiek nazwa (np. "Moje konto")
   - Login: Numer karty Medicover
   - Hasło: Hasło do Medicover
4. **Kliknij "Dodaj Profil"**

### Wyszukaj Wizyty!

1. **Przejdź do "Wyszukaj"**
2. **Wybierz profil**
3. **Wpisz specjalność** (np. "Kardiologia")
4. **Ustaw godziny i dni**
5. **Kliknij "Szukaj Wizyt"**
6. **Zarezerwuj!**

---

## Gdzieś Się Zacięło? 🤔

### "Port w użyciu" - OK, Railway to obsłuży automatycznie ✅

### "Nie mam Railway CLI"

**Alternatywa - Wdróż przez GitHub:**
1. Wejdź na https://railway.app
2. Kliknij "Create New Project"
3. Wybierz "Deploy from GitHub"
4. Połącz swoje repo
5. Wybierz gałąź `railway-deployment`
6. Railway wdroży automatycznie! ✅

### "Logi pokazują błąd Chrome"

Nie martw się - Dockerfile ma wszystko zainstalowane. Czekaj ~2 minuty na pełny startup.

Sprawdź logi:
```bash
railway logs --follow
```

### "Wyszukiwanie czasuje się"

To normalne - WebDriver potrzebuje czasu. Timeout wynosi 60 sekund.
Spróbuj zmniejszyć filtry.

---

## Zmienne Środowiskowe (Opcjonalnie)

W Railway Dashboard → Project Settings → Variables:

```env
FLASK_ENV=production
FLASK_DEBUG=False
LOG_LEVEL=INFO
```

Zbędne - juž ustawione w kodzie!

---

## Monitorowanie Aplikacji

### W Railway Dashboard:
- **Logs** - Logi aplikacji (kliknij projekt → Logs)
- **Metrics** - CPU, Memory, Network
- **Deployments** - Historia wdrożeń

### Terminal:
```bash
# Obserwuj logi na żywo
railway logs --follow

# Sprawdź status
railway status

# Lista projektów
railway projects
```

---

## Aktualizacje

Zacommituj zmiany i push - Railway wdroży automatycznie:

```bash
git add .
git commit -m "Feature: [opis zmian]"
git push origin railway-deployment
```

---

## Przydatne Linki

- 📚 [Pełny Przewodnik](DEPLOYMENT_GUIDE.md)
- 📖 [Dokumentacja](README_WEB.md)
- 🔧 [Railway Docs](https://docs.railway.app)
- 🐛 [GitHub Issues](https://github.com/AdamWojciechowskiPL/Medifinder/issues)

---

## Potrzebujesz Pomocy?

1. Sprawdź logi: `railway logs`
2. Przeczytaj [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. Otwórz Issue na GitHub
4. Kontaktuj support Railway: https://railway.app/support

---

**Powodzenia! 🚀**

Teraz masz Medifinder zawsze dostępny w chmurze!

💡 **Tip:** Bookmark URL aplikacji - będzie Ci potrzebny!

---

*Medifinder 1.0.0 | Railway Deployment | 2026*
