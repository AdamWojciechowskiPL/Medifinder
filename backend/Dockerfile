FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver

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

# KLUCZOWA ZMIANA: Railway buduje z root-a repo, więc kopiujemy z backend/
WORKDIR /app/backend

# Kopiujemy requirements Z PODKATALOGU backend (kontekst Railway = root repo)
COPY backend/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopiujemy CAŁY backend do /app/backend
COPY backend/ .

# Tworzymy katalogi na config
RUN mkdir -p /app/backend/config /app/backend/app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Startujemy gunicorn - main.py jest teraz w /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
