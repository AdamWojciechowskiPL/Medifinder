FROM python:3.11-slim

# Ustawienie zmiennych środowiskowych
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    PATH=/app/.venv/bin:$PATH

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

# Instalacja zależności Pythona z verbose logowaniem
RUN echo "=== Upgrading pip, setuptools, wheel ===" && \
    pip install --upgrade pip setuptools wheel && \
    echo "=== Installing requirements from requirements.txt ===" && \
    pip install -v -r requirements.txt && \
    echo "=== Verifying gunicorn installation ===" && \
    which gunicorn && \
    gunicorn --version && \
    echo "=== Requirements installation complete ==="

# Kopiowanie całej aplikacji
COPY . .

# Stworzenie katalogów dla konfiguracji
RUN mkdir -p /app/config /app/app && \
    echo "=== Verifying Python installation ===" && \
    python --version && \
    pip list | grep -i gunicorn

# Port, na którym będzie działać aplikacja
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Debug: sprawdzenie co jest w /app
RUN echo "=== Contents of /app ===" && ls -la /app/ && \
    echo "=== Python path ===" && python -c "import sys; print('\n'.join(sys.path))" && \
    echo "=== Attempting to import Flask ===" && python -c "import flask; print(f'Flask version: {flask.__version__}')"

# Uruchomienie aplikacji za pośrednictwem gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
