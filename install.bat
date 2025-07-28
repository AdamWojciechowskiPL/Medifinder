@echo off
:: ============================================================================
:: :: Instalator Zależności dla Medicover Appointment Finder
:: :: Wersja 1.0
:: ::
:: :: Ten skrypt automatycznie:
:: :: 1. Sprawdza, czy Python jest zainstalowany i dostępny.
:: :: 2. Tworzy dedykowane środowisko wirtualne w folderze 'venv'.
:: :: 3. Instaluje wszystkie wymagane biblioteki z pliku requirements.txt.
:: ============================================================================

title Medicover App Installer

echo.
echo  Witamy w instalatorze aplikacji Medicover Appointment Finder!
echo.
echo  Ten skrypt przygotuje srodowisko do uruchomienia aplikacji.
echo  Proces moze potrwac kilka minut. Prosze nie zamykac tego okna.
echo.
echo  -----------------------------------------------------------------
pause
echo.

:: Krok 1: Sprawdzenie, czy Python jest dostępny w systemie
echo  [1/3] Sprawdzanie dostepnosci Pythona...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo  BLAD: Nie znaleziono Pythona!
    echo.
    echo  Upewnij sie, ze Python 3.9+ jest zainstalowany i ze podczas
    echo  instalacji zaznaczono opcje "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
echo  OK - Python jest dostepny.
echo.

:: Krok 2: Tworzenie środowiska wirtualnego (jeśli jeszcze nie istnieje)
echo  [2/3] Przygotowywanie srodowiska wirtualnego...
if not exist venv (
    echo  Tworzenie nowego srodowiska w folderze 'venv'...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo.
        echo  BLAD: Nie udalo sie utworzyc srodowiska wirtualnego.
        echo.
        pause
        exit /b 1
    )
) else (
    echo  Srodowisko 'venv' juz istnieje, pomijanie.
)
echo  OK - Srodowisko gotowe.
echo.

:: Krok 3: Aktywacja środowiska i instalacja bibliotek
echo  [3/3] Instalowanie wymaganych bibliotek...
echo  To moze potrwac chwile, prosze czekac...
echo.

:: Aktywujemy środowisko
call "venv\Scripts\activate.bat"

:: Instalujemy biblioteki
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo  BLAD: Wystapil problem podczas instalacji bibliotek.
    echo  Sprawdz polaczenie z internetem i sprobuj ponownie.
    echo.
    pause
    exit /b 1
)

echo.
echo  -----------------------------------------------------------------
echo.
echo  Instalacja zakonczona sukcesem!
echo.
echo  Aby uruchomic aplikacje, uzyj pliku 'start.bat'.
echo.
pause
exit /b 0