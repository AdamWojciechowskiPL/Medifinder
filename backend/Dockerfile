FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    PYTHONPATH=/app

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

WORKDIR /app

# Kopiujemy requirements
COPY backend/requirements.txt ./backend/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r ./backend/requirements.txt

# Kopiujemy CAŁY folder app/ (z MedicoverApp)
COPY app/ ./app/

# Kopiujemy backend
COPY backend/ ./backend/

# Kopiujemy config (jeśli potrzebny)
COPY config/ ./config/

# Tworzymy dodatkowe katalogi
RUN mkdir -p /app/backend/config /app/backend/app

# Railway dynamicznie ustawia PORT - nie hardcoduj
EXPOSE ${PORT:-5000}

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-5000}/health || exit 1

# Startujemy z katalogu backend
WORKDIR /app/backend

# KLUCZOWA ZMIANA: Użyj zmiennej środowiskowej PORT z Railway
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 --access-logfile - --error-logfile - main:app
