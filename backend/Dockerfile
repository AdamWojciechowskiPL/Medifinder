FROM python:3.11-slim

# Ustawienie zmiennych środowiskowych
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver

# Zainstalowanie systemowych zależności (Chromium i ChromeDriver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    xdg-utils \
    libxss1 \
    lsb-release \
    xvfb \
    ca-certificates \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Ustawienie katalogu roboczego
WORKDIR /app

# Kopiowanie pliku requirements
COPY requirements.txt .

# Instalacja zależności Pythona
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopiowanie całej aplikacji
COPY . .

# Stworzenie katalogów dla konfiguracji
RUN mkdir -p /app/config /app/app

# Port, na którym będzie działać aplikacja
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Uruchomienie aplikacji
# Najpierw staramy się z gunicorn (jeśli zainstalowany), jeśli nie - używamy python -m flask
CMD gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 --access-logfile - --error-logfile - main:app || python -m flask run --host 0.0.0.0 --port 5000
