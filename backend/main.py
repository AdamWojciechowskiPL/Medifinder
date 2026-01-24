import os
import sys
import logging
from pathlib import Path
from datetime import datetime, date

from flask import Flask, jsonify, request, session, redirect, url_for, send_from_directory
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# Konfiguracja ścieżek
ROOT_DIR = Path(__file__).parent.parent.resolve()  # /app (parent of /app/backend)
APP_DIR = ROOT_DIR / "app"
CONFIG_DIR = ROOT_DIR / "config"
FRONTEND_DIR = ROOT_DIR / "frontend"  # Ścieżka do plików frontendowych

# Upewnij się, że katalogi istnieją i są w PYTHONPATH
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Konfiguracja Flask do serwowania plików statycznych z folderu frontend
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
# Konfiguracja dla reverse proxy (np. Railway)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# === KONFIGURACJA SESJI ===
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Przy Single Origin (serwowanie frontu z backendu) te ustawienia są bezpieczniejsze i prostsze
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' 
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# CORS - teraz technicznie mniej potrzebny, ale zostawiamy dla developmentu
CORS(app, supports_credentials=True)

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
    from app.main import MedicoverApp
    logger.info("✅ MedicoverApp zaimportowany poprawnie")
except ImportError as e:
    logger.error(f"❌ Nie można zaimportować MedicoverApp: {e}")

def init_app():
    global med_app
    try:
        med_app = MedicoverApp(CONFIG_DIR)
        logger.info("✅ Medifinder zainicjalizowany")
        return True
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji: {e}", exc_info=True)
        return False

# ======== SERWOWANIE FRONTENDU (Single Origin) =========

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ======== AUTH =========

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
    if not getattr(oauth, 'google', None):
        return jsonify({'success': False, 'error': 'OAuth nie jest skonfigurowany'}), 500
    redirect_uri = url_for('auth_callback', _external=True, _scheme='https')
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.userinfo()
        session['user'] = {
            'email': user_info.get('email'),
            'name': user_info.get('name')
        }
        logger.info(f"🔐 Zalogowano użytkownika {session['user']['email']}")
        # Przekierowanie na stronę główną (tą samą domenę)
        return redirect('/')
    except Exception as e:
        logger.error(f"❌ Błąd autoryzacji: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

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

# ======== API ENDPOINTS (Bez zmian logiki, tylko prefix) =========

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'service': 'Medifinder API', 'version': '1.3.0'}), 200

@app.route('/api/v1/profiles', methods=['GET'])
@require_login
def get_profiles():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        profiles = med_app.get_available_profiles()
        return jsonify({'success': True, 'data': profiles, 'count': len(profiles)}), 200
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/profiles/add', methods=['POST'])
@require_login
def add_profile():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = request.get_json() or {}
        med_app.add_profile(data.get('login'), data.get('password'), data.get('name'))
        return jsonify({'success': True, 'message': 'Profil dodany'}), 201
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/specialties', methods=['GET'])
@require_login
def get_specialties():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        profile_name = request.args.get('profile')
        is_child = False
        if profile_name:
            prof = med_app.profile_manager.get_profile(profile_name)
            if prof: is_child = prof.is_child_account
        
        data = med_app.specialty_manager.data
        result = []
        for name, details in data.items():
            if is_child:
                if not details.get("for_adult_account_only", False):
                    result.append({"name": name, "ids": details["ids"]})
            else:
                if not details.get("for_child_account_only", False):
                    result.append({"name": name, "ids": details["ids"]})
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/doctors', methods=['GET'])
@require_login
def get_doctors():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = med_app.doctor_manager.get_all_doctors_data()
        result = [{"name": k, "id": v["id"], "specialty_ids": v.get("specialty_ids", [])} for k, v in data.items()]
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/clinics', methods=['GET'])
@require_login
def get_clinics():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = med_app.clinic_manager.data
        result = [{"name": k, "id": v["id"]} for k, v in data.items()]
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/appointments/search', methods=['POST'])
@require_login
def search_appointments():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = request.get_json() or {}
        results = med_app.search_appointments(
            profile=data.get('profile'),
            specialty_ids=data.get('specialty_ids'),
            doctor_ids=data.get('doctor_ids'),
            clinic_ids=data.get('clinic_ids'),
            preferred_days=data.get('preferred_days', []),
            time_range=data.get('time_range'),
            day_time_ranges=data.get('day_time_ranges'),
            excluded_dates=[date.fromisoformat(d) for d in data.get('excluded_dates', [])],
            headless=True
        )
        return jsonify({'success': True, 'count': len(results), 'data': results}), 200
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/appointments/book', methods=['POST'])
@require_login
def book_appointment():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = request.get_json() or {}
        result = med_app.book_appointment(profile=data.get('profile'), appointment_id=data.get('appointment_id'))
        return jsonify({'success': True, 'message': 'Rezerwacja OK', 'data': result}), 200
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    if not init_app(): sys.exit(1)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG')=='True', threaded=True)
