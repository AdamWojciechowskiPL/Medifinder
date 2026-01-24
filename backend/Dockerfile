FROM python:3.11-slim

# Ustawienie zmiennych środowiskowych
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Zainstalowanie systemowych zależności (Chrome i ChromeDriver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium-browser \
    chromium-driver \
    fonts-liberation \
    xdg-utils \
    libu1 \
    libappindicator1 \
    libindicator7 \
    libxss1 \
    lsb-release \
    xvfb \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Ustawienie katalogu roboczego
WORKDIR /app

# Kopiowanie pliku requirements
COPY requirements.txt .

# Instalacja zależności Pythona
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Kopiowanie całej aplikacji
COPY . .

# Stworzenie katalogów dla konfiguracji
RUN mkdir -p /app/config /app/app

# Port, na którym będzie działać aplikacja
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Uruchomienie aplikacji za pośrednictwem gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
