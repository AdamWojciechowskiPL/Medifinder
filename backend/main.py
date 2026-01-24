# backend/main.py

# ... (imports remain the same)
import os
import sys
import shutil
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
ROOT_DIR = Path(__file__).parent.parent.resolve()
APP_DIR = ROOT_DIR / "app"
CONFIG_DIR = ROOT_DIR / "config"
SEED_DIR = ROOT_DIR / "config_seed"  # Nowy katalog z danymi startowymi
FRONTEND_DIR = ROOT_DIR / "frontend"

sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- SEEDING LOGIC ---
def seed_config_files():
    """
    Sprawdza, czy w katalogu CONFIG_DIR (volume) brakuje plików json.
    Jeśli tak, kopiuje je z katalogu SEED_DIR (obraz dockera).
    """
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Utworzono katalog konfiguracyjny: {CONFIG_DIR}")

    files_to_seed = ["specialties.json", "clinics.json", "doctors.json", "profiles.json"]
    
    if SEED_DIR.exists():
        for filename in files_to_seed:
            src = SEED_DIR / filename
            dst = CONFIG_DIR / filename
            
            should_copy = False
            
            if src.exists():
                if not dst.exists():
                    should_copy = True
                    logger.info(f"📄 Plik {filename} nie istnieje w volume. Kopiowanie...")
                else:
                    # Sprawdź czy plik jest pusty (lub prawie pusty, np. "{}")
                    try:
                        size = dst.stat().st_size
                        # Jeśli plik jest mniejszy niż 10 bajtów, zakładamy że jest pusty/uszkodzony
                        # i nadpisujemy go danymi z seeda (chyba że to profiles.json, tu ostrożnie)
                        if size < 10 and filename != "profiles.json":
                            should_copy = True
                            logger.warning(f"⚠️ Plik {filename} w volume jest pusty ({size}B). Nadpisywanie z seeda.")
                        
                        # Dla specialties.json zawsze wymuszamy nadpisanie jeśli jest mniejszy niż seed (np. pusty vs pełny)
                        # bo to słownik statyczny
                        if filename == "specialties.json" and size < src.stat().st_size:
                             should_copy = True
                             logger.warning(f"⚠️ Słownik {filename} wygląda na niekompletny. Aktualizacja z seeda.")
                             
                    except Exception as e:
                        logger.error(f"Błąd sprawdzania pliku {dst}: {e}")
            
                if should_copy:
                    try:
                        shutil.copy2(src, dst)
                        logger.info(f"✅ Skopiowano {filename} z seed do volume.")
                    except Exception as e:
                        logger.error(f"❌ Błąd kopiowania {filename}: {e}")
            elif not src.exists() and filename != "profiles.json":
                logger.warning(f"⚠️ Brak pliku źródłowego {filename} w {SEED_DIR}")
    else:
        logger.warning(f"⚠️ Katalog SEED_DIR {SEED_DIR} nie istnieje. Pomijam seedowanie.")

# Uruchom seedowanie przed startem aplikacji
seed_config_files()

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' 
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

CORS(app, supports_credentials=True)

oauth = OAuth(app)
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['GOOGLE_DISCOVERY_URL'] = "https://accounts.google.com/.well-known/openid-configuration"

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
    try:
        med_app = MedicoverApp(CONFIG_DIR)
        logger.info("✅ Medifinder zainicjalizowany globalnie")
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji instancji MedicoverApp: {e}", exc_info=True)
except ImportError as e:
    logger.error(f"❌ Nie można zaimportować klasy MedicoverApp: {e}")

# Helper to get current user email
def get_current_user_email():
    if 'user' in session:
        return session['user'].get('email')
    return None

# ======== API & AUTH ROUTES =========

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'service': 'Medifinder API', 'version': '1.3.2'}), 200

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

# API V1
@app.route('/api/v1/profiles', methods=['GET'])
@require_login
def get_profiles():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    try:
        # Pass user_email to get scoped profiles
        profiles = med_app.get_available_profiles(user_email)
        return jsonify({'success': True, 'data': profiles, 'count': len(profiles)}), 200
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/profiles/add', methods=['POST'])
@require_login
def add_profile():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    try:
        data = request.get_json() or {}
        # Pass user_email to bind profile to this user
        med_app.add_profile(
            user_email=user_email,
            login=data.get('login'), 
            password=data.get('password'), 
            name=data.get('name'),
            is_child_account=data.get('is_child_account', False) # Odbieramy flagę dziecka
        )
        return jsonify({'success': True, 'message': 'Profil dodany'}), 201
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/specialties', methods=['GET'])
@require_login
def get_specialties():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    try:
        profile_name = request.args.get('profile')
        is_child = False
        if profile_name:
            # Pass user_email to look up correct profile
            prof = med_app.profile_manager.get_profile(user_email, profile_name)
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
    user_email = get_current_user_email()
    try:
        data = request.get_json() or {}
        results = med_app.search_appointments(
            user_email=user_email, # NEW: Context passed
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
    user_email = get_current_user_email()
    try:
        data = request.get_json() or {}
        result = med_app.book_appointment(
            user_email=user_email, # NEW: Context passed
            profile=data.get('profile'), 
            appointment_id=data.get('appointment_id')
        )
        return jsonify({'success': True, 'message': 'Rezerwacja OK', 'data': result}), 200
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

# ======== SERVING FRONTEND =========
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/') or path.startswith('auth/'):
        return jsonify({'error': 'Not found'}), 404
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    if not med_app: logger.error("Global init failed")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG')=='True', threaded=True)
