import os
import sys
import logging
from pathlib import Path
from datetime import datetime, date

from flask import Flask, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# Konfiguracja ścieżek
ROOT_DIR = Path(__file__).parent.resolve()
APP_DIR = ROOT_DIR / "app"
CONFIG_DIR = ROOT_DIR / "config"

APP_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(APP_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Sekret dla sesji (USTAW w env w Railway!)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Konfiguracja OAuth (Google)
oauth = OAuth(app)
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['GOOGLE_DISCOVERY_URL'] = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

if app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET']:
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
        client_kwargs={'scope': 'openid email profile'}
    )

med_app = None

try:
    from main import MedicoverApp
except ImportError as e:
    logger.error(f"Nie można zaimportować MedicoverApp: {e}")


def init_app():
    global med_app
    try:
        med_app = MedicoverApp(CONFIG_DIR)
        logger.info("✅ Medifinder zainicjalizowany")
        return True
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji: {e}")
        return False


# ======== POMOCNICY AUTH =========

def require_login(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'Nieautoryzowany'}), 401
        return fn(*args, **kwargs)

    return wrapper


@app.route('/auth/login')
def auth_login():
    if 'google' not in oauth:
        return jsonify({'success': False, 'error': 'OAuth nie jest skonfigurowany'}), 500
    redirect_uri = url_for('auth_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth/callback')
def auth_callback():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.parse_id_token(token)
    session['user'] = {
        'email': user_info.get('email'),
        'name': user_info.get('name')
    }
    logger.info(f"🔐 Zalogowano użytkownika {session['user']['email']}")
    return redirect(os.environ.get('FRONTEND_URL', '/'))


@app.route('/auth/logout', methods=['POST'])
@require_login
def auth_logout():
    session.pop('user', None)
    return jsonify({'success': True})


@app.route('/auth/me')
def auth_me():
    if 'user' not in session:
        return jsonify({'authenticated': False})
    return jsonify({'authenticated': True, 'user': session['user']})


# ======== HEALTH =========

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'service': 'Medifinder API', 'version': '1.1.0'}), 200


# ======== PROFILES =========

@app.route('/api/v1/profiles', methods=['GET'])
@require_login
def get_profiles():
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    try:
        profiles = med_app.get_available_profiles()
        return jsonify({'success': True, 'data': profiles, 'count': len(profiles)}), 200
    except Exception as e:
        logger.error(f"Błąd profili: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/profiles/add', methods=['POST'])
@require_login
def add_profile():
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    try:
        data = request.get_json() or {}
        required_fields = ['login', 'password', 'name']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': f'Brakuje pól: {required_fields}'}), 400
        result = med_app.add_profile(
            login=data['login'],
            password=data['password'],
            name=data['name']
        )
        return jsonify({'success': True, 'message': f'Profil "{data["name"]}" dodany', 'data': result}), 201
    except Exception as e:
        logger.error(f"Błąd dodawania profilu: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ======== APPOINTMENTS (rozszerzone filtrowanie) =========

@app.route('/api/v1/appointments/search', methods=['POST'])
@require_login
def search_appointments():
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    try:
        data = request.get_json() or {}
        if 'profile' not in data:
            return jsonify({'success': False, 'error': 'Wymagane pole: profile'}), 400

        # nowe pola filtrowania
        # day_time_ranges: {"1": {"start": "08:00", "end": "16:00"}, "2": {...}, ...}
        day_time_ranges = data.get('day_time_ranges')
        preferred_days = data.get('preferred_days', [])
        time_range = data.get('time_range')
        excluded_dates = data.get('excluded_dates', [])  # lista stringów YYYY-MM-DD

        logger.info(f"🔍 Wyszukiwanie wizyt – profil={data.get('profile')}, specialty={data.get('specialty')}")
        logger.info(f"Dni: {preferred_days}, day_time_ranges={day_time_ranges}, excluded={excluded_dates}")

        results = med_app.search_appointments(
            profile=data.get('profile'),
            specialty=data.get('specialty', ''),
            doctors=data.get('doctors', []),
            clinics=data.get('clinics', []),
            preferred_days=preferred_days,
            time_range=time_range,
            day_time_ranges=day_time_ranges,
            excluded_dates=[date.fromisoformat(d) for d in excluded_dates],
            headless=True
        )
        return jsonify({'success': True, 'count': len(results), 'data': results}), 200
    except Exception as e:
        logger.error(f"Błąd wyszukiwania: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/appointments/auto-book', methods=['POST'])
@require_login
def auto_book_appointment():
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    try:
        data = request.get_json() or {}
        required_fields = ['profile', 'specialty']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': f'Brakuje pól: {required_fields}'}), 400

        day_time_ranges = data.get('day_time_ranges')
        preferred_days = data.get('preferred_days', [1, 2, 3, 4, 5])
        time_range = data.get('time_range', {'start': '08:00', 'end': '20:00'})
        excluded_dates = data.get('excluded_dates', [])

        auto_params = {
            'profile': data['profile'],
            'specialty': data['specialty'],
            'doctors': data.get('doctors', []),
            'clinics': data.get('clinics', []),
            'preferred_days': preferred_days,
            'time_range': time_range,
            'day_time_ranges': day_time_ranges,
            'excluded_dates': [date.fromisoformat(d) for d in excluded_dates],
            'auto_book': True,
            'headless': True
        }
        logger.info(f"🤖 Auto-book params: {auto_params}")

        result = med_app.auto_book_appointment(**auto_params)
        return jsonify({'success': True, 'message': 'Automatyczna rezerwacja uruchomiona', 'data': result}), 200
    except Exception as e:
        logger.error(f"Błąd auto-book: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/appointments/book', methods=['POST'])
@require_login
def book_appointment():
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    try:
        data = request.get_json() or {}
        required_fields = ['profile', 'appointment_id']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': f'Brakuje pól: {required_fields}'}), 400
        result = med_app.book_appointment(
            profile=data['profile'],
            appointment_id=data['appointment_id']
        )
        return jsonify({'success': True, 'message': 'Wizyta zarezerwowana', 'data': result}), 200
    except Exception as e:
        logger.error(f"Błąd rezerwacji: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint nie znaleziony'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Wewnętrzny błąd: {error}")
    return jsonify({'success': False, 'error': 'Wewnętrzny błąd serwera'}), 500


if __name__ == '__main__':
    if not init_app():
        logger.error("Nie udało się zainicjalizować aplikacji")
        sys.exit(1)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    logger.info(f"🚀 Start API na porcie {port}")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
