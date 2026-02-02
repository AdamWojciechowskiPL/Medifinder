import os
import sys
import shutil
import logging
import json
import atexit
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
SEED_DIR = ROOT_DIR / "config_seed"
FRONTEND_DIR = ROOT_DIR / "frontend"

sys.path.insert(0, str(ROOT_DIR))

# Konfiguracja logowania z DEBUG i force flush dla Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# Force unbuffered output dla Railway
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("🚀 MEDIFINDER START - LOG LEVEL: INFO")
logger.info("=" * 80)

# --- SEEDING LOGIC ---
def seed_config_files():
    """
    Sprawdza, czy w katalogu CONFIG_DIR (volume) brakuje plików json.
    Jeśli tak, kopiuje je z katalogu SEED_DIR (obraz dockera).
    """
    logger.info(f"🚀 ROZPOCZYNAM SEEDOWANIE KONFIGURACJI")
    logger.info(f"📂 ROOT_DIR: {ROOT_DIR}")
    logger.info(f"📂 CONFIG_DIR: {CONFIG_DIR} (exists: {CONFIG_DIR.exists()})")
    logger.info(f"📂 SEED_DIR: {SEED_DIR} (exists: {SEED_DIR.exists()})")

    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Utworzono katalog konfiguracyjny: {CONFIG_DIR}")

    files_to_seed = ["specialties.json", "clinics.json", "doctors.json", "profiles.json"]
    
    if SEED_DIR.exists():
        for filename in files_to_seed:
            src = SEED_DIR / filename
            dst = CONFIG_DIR / filename
            
            should_copy = False
            reason = ""
            
            if src.exists():
                if not dst.exists():
                    should_copy = True
                    reason = "Brak pliku docelowego"
                else:
                    try:
                        src_size = src.stat().st_size
                        dst_size = dst.stat().st_size
                        
                        logger.info(f"🔍 {filename}: SRC={src_size}B, DST={dst_size}B")

                        if dst_size < 10 and filename != "profiles.json":
                            should_copy = True
                            reason = f"Plik docelowy zbyt mały ({dst_size}B)"
                        
                        elif filename != "profiles.json":
                            with open(dst, 'r', encoding='utf-8') as f:
                                try:
                                    first_chars = f.read(50)
                                    if '"type":"file"' in first_chars or '"type": "file"' in first_chars:
                                        should_copy = True
                                        reason = "Wykryto błędną zawartość (metadane zamiast danych)"
                                except Exception:
                                    pass

                        if not should_copy and filename in ["specialties.json", "clinics.json", "doctors.json"]:
                             if dst_size < src_size * 0.8:
                                 should_copy = True
                                 reason = f"Plik docelowy znacznie mniejszy od oryginału ({dst_size}B < {src_size}B)"
                             
                    except Exception as e:
                        logger.error(f"Błąd sprawdzania pliku {dst}: {e}")
            
                if should_copy:
                    try:
                        shutil.copy2(src, dst)
                        logger.info(f"✅ Skopiowano {filename}: {reason}")
                    except Exception as e:
                        logger.error(f"❌ Błąd kopiowania {filename}: {e}")
                else:
                    logger.info(f"⏭️ Pominięto {filename}: Plik wygląda OK")
            elif not src.exists() and filename != "profiles.json":
                logger.warning(f"⚠️ Brak pliku źródłowego {filename} w {SEED_DIR}")
    else:
        logger.warning(f"⚠️ Katalog SEED_DIR {SEED_DIR} nie istnieje. Pomijam seedowanie.")

# Uruchom seedowanie przed startem aplikacji
seed_config_files()

logger.info("🔧 Inicjalizacja Flask...")
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' 
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

CORS(app, supports_credentials=True)
logger.info("✅ Flask skonfigurowany")

logger.info("🔐 Konfiguracja OAuth...")
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
    logger.info("✅ OAuth Google skonfigurowany")
else:
    logger.warning("⚠️ Brak konfiguracji OAuth (sprawdź zmienne środowiskowe)")

med_app = None
scheduler = None

try:
    logger.info("📦 Import MedicoverApp...")
    from app.main import MedicoverApp
    from backend.scheduler import MedifinderScheduler
    logger.info("✅ MedicoverApp zaimportowany poprawnie")
    try:
        logger.info("🏗️ Inicjalizacja MedicoverApp...")
        med_app = MedicoverApp(CONFIG_DIR)
        logger.info("✅ Medifinder zainicjalizowany globalnie")
        
        # Inicjalizacja schedulera
        logger.info("⏱️ Inicjalizacja schedulera...")
        scheduler = MedifinderScheduler(CONFIG_DIR, med_app)
        logger.info("✅ Scheduler zainicjalizowany")
        
        # Zamknij scheduler przy wyłączeniu aplikacji
        atexit.register(lambda: scheduler.shutdown() if scheduler else None)
        
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji: {e}", exc_info=True)
except ImportError as e:
    logger.error(f"❌ Nie można zaimportować: {e}")

# Helper to get current user email
def get_current_user_email():
    if 'user' in session:
        return session['user'].get('email')
    return None

def require_login(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'Nieautoryzowany'}), 401
        return fn(*args, **kwargs)
    return wrapper

# ======== API & AUTH ROUTES =========

@app.route('/health', methods=['GET'])
def health_check():
    logger.debug("Health check called")
    return jsonify({'status': 'ok', 'service': 'Medifinder API', 'version': '2.0.0'}), 200

@app.route('/api/v1/debug/config', methods=['GET'])
@require_login
def debug_config():
    """Sprawdza stan plików konfiguracyjnych. WYMAGA LOGOWANIA."""
    logger.debug("Debug config endpoint called")
    status = {
        "config_dir": str(CONFIG_DIR),
        "seed_dir": str(SEED_DIR),
        "files": {}
    }
    
    for fname in ["specialties.json", "doctors.json", "clinics.json"]:
        fpath = CONFIG_DIR / fname
        fseed = SEED_DIR / fname
        
        file_info = {
            "exists": fpath.exists(),
            "size": fpath.stat().st_size if fpath.exists() else -1,
            "seed_exists": fseed.exists(),
            "seed_size": fseed.stat().st_size if fseed.exists() else -1,
        }
        
        if fpath.exists():
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read(100)
                    file_info["head"] = content
            except Exception as e:
                file_info["error"] = str(e)
                
        status["files"][fname] = file_info
        
    return jsonify(status)

@app.route('/auth/login')
def auth_login():
    logger.info("Auth login request received")
    if not getattr(oauth, 'google', None):
        logger.error("OAuth nie jest skonfigurowany")
        return jsonify({'success': False, 'error': 'OAuth nie jest skonfigurowany'}), 500
    redirect_uri = url_for('auth_callback', _external=True, _scheme='https')
    logger.debug(f"Redirect URI: {redirect_uri}")
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    logger.info("Auth callback received")
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
    user_email = get_current_user_email()
    logger.info(f"Wylogowanie użytkownika {user_email}")
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/auth/me')
def auth_me():
    if 'user' not in session:
        logger.debug("Auth check: not authenticated")
        return jsonify({'authenticated': False})
    logger.debug(f"Auth check: {session['user']['email']}")
    return jsonify({'authenticated': True, 'user': session['user']})

# ======== SCHEDULER API =========

@app.route('/api/v1/scheduler/start', methods=['POST'])
@require_login
def scheduler_start():
    """Uruchamia zadanie cyklicznego sprawdzania dla użytkownika."""
    logger.info("Scheduler start request")
    if not scheduler:
        logger.error("Scheduler nie jest zainicjalizowany")
        return jsonify({'success': False, 'error': 'Scheduler nie jest zainicjalizowany'}), 500
    
    user_email = get_current_user_email()
    data = request.get_json() or {}
    logger.debug(f"Scheduler start data: {data}")
    
    try:
        result = scheduler.start_task(
            user_email=user_email,
            profile=data.get('profile'),
            search_params={
                'specialty_ids': data.get('specialty_ids', []),
                'doctor_ids': data.get('doctor_ids', []),
                'clinic_ids': data.get('clinic_ids', []),
                'preferred_days': data.get('preferred_days', []),
                'time_range': data.get('time_range'),
                'excluded_dates': data.get('excluded_dates', []),
                'day_time_ranges': data.get('day_time_ranges', {}),
                'start_date': data.get('start_date'),
                'end_date': data.get('end_date'),
                'min_lead_time': data.get('min_lead_time') # Pass new param
            },
            interval_minutes=data.get('interval_minutes', 5),
            auto_book=data.get('auto_book', False),
            twin_profile=data.get('twin_profile')
        )
        if not result.get('success'):
             logger.warning(f"Scheduler start failed: {result.get('error')}")
             return jsonify(result), 409

        logger.info(f"Scheduler started successfully for {user_email}")
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Błąd uruchamiania zadania: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/scheduler/stop', methods=['POST'])
@require_login
def scheduler_stop():
    """Zatrzymuje zadanie cyklicznego sprawdzania."""
    logger.info("Scheduler stop request")
    if not scheduler:
        return jsonify({'success': False, 'error': 'Scheduler nie jest zainicjalizowany'}), 500
    
    user_email = get_current_user_email()
    data = request.get_json() or {}
    
    try:
        result = scheduler.stop_task(user_email, data.get('profile'))
        logger.info(f"Scheduler stopped for {user_email}")
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Błąd zatrzymywania zadania: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/scheduler/status', methods=['GET'])
@require_login
def scheduler_status():
    """Zwraca status zadania dla użytkownika i profilu."""
    if not scheduler:
        return jsonify({'success': False, 'error': 'Scheduler nie jest zainicjalizowany'}), 500
    
    user_email = get_current_user_email()
    profile = request.args.get('profile')
    
    if not profile:
        return jsonify({'success': False, 'error': 'Brak parametru profile'}), 400
    
    try:
        status = scheduler.get_task_status(user_email, profile)
        if status:
            logger.debug(f"Scheduler status for {user_email}/{profile}: active")
            return jsonify({'success': True, 'data': status}), 200
        else:
            logger.debug(f"Scheduler status for {user_email}/{profile}: inactive")
            return jsonify({'success': True, 'data': None, 'message': 'Brak aktywnego zadania'}), 200
    except Exception as e:
        logger.error(f"Błąd pobierania statusu: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/scheduler/results', methods=['GET'])
@require_login
def scheduler_results():
    """Zwraca ostatnie wyniki wyszukiwania z schedulera."""
    if not scheduler:
        return jsonify({'success': False, 'error': 'Scheduler nie jest zainicjalizowany'}), 500
    
    user_email = get_current_user_email()
    profile = request.args.get('profile')
    
    if not profile:
        return jsonify({'success': False, 'error': 'Brak parametru profile'}), 400
    
    try:
        results = scheduler.get_last_results(user_email, profile)
        if results:
            logger.debug(f"Scheduler results for {user_email}/{profile}: {len(results.get('appointments', []))} appointments")
            return jsonify({'success': True, 'data': results}), 200
        else:
            logger.debug(f"Scheduler results for {user_email}/{profile}: no results")
            return jsonify({'success': True, 'data': None, 'message': 'Brak wyników'}), 200
    except Exception as e:
        logger.error(f"Błąd pobierania wyników: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ======== PROFILES API =========

@app.route('/api/v1/profiles', methods=['GET'])
@require_login
def get_profiles():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    logger.debug(f"Getting profiles for {user_email}")
    try:
        profiles = med_app.get_available_profiles(user_email)
        logger.info(f"Found {len(profiles)} profiles for {user_email}")
        return jsonify({'success': True, 'data': profiles, 'count': len(profiles)}), 200\n    except Exception as e: 
        logger.error(f"Error getting profiles: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/profiles/add', methods=['POST'])
@require_login
def add_profile():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    logger.info(f"Adding profile for {user_email}")
    try:
        # Check profiles limit per user
        current_profiles = med_app.get_available_profiles(user_email)
        if len(current_profiles) >= 5:
            logger.warning(f"Profile limit reached for {user_email}")
            return jsonify({'success': False, 'error': 'Osiągnięto limit 5 profili'}), 400

        data = request.get_json() or {}
        med_app.add_profile(
            user_email=user_email,
            login=data.get('login'), 
            password=data.get('password'), 
            name=data.get('name'),
            is_child_account=data.get('is_child_account', False)
        )
        logger.info(f"Profile added successfully for {user_email}")
        return jsonify({'success': True, 'message': 'Profil dodany'}), 201
    except Exception as e: 
        logger.error(f"Error adding profile: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ======== DICTIONARIES API =========

@app.route('/api/v1/dictionaries/specialties', methods=['GET'])
@require_login
def get_specialties():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    try:
        profile_name = request.args.get('profile')
        is_child = False
        if profile_name:
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
        logger.debug(f"Returning {len(result)} specialties")
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: 
        logger.error(f"Error getting specialties: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/doctors', methods=['GET'])
@require_login
def get_doctors():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = med_app.doctor_manager.get_all_doctors_data()
        result = [{"name": k, "id": v["id"], "specialty_ids": v.get("specialty_ids", [])} for k, v in data.items()]
        logger.debug(f"Returning {len(result)} doctors")
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: 
        logger.error(f"Error getting doctors: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/dictionaries/clinics', methods=['GET'])
@require_login
def get_clinics():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    try:
        data = med_app.clinic_manager.data
        result = [{"name": k, "id": v["id"]} for k, v in data.items()]
        logger.debug(f"Returning {len(result)} clinics")
        return jsonify({'success': True, 'data': sorted(result, key=lambda x: x['name'])})
    except Exception as e: 
        logger.error(f"Error getting clinics: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ======== APPOINTMENTS API =========

@app.route('/api/v1/appointments/search', methods=['POST'])
@require_login
def search_appointments():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    logger.info(f"Search appointments request from {user_email}")
    try:
        data = request.get_json() or {}
        
        specialty_ids = data.get('specialty_ids')
        if not specialty_ids or len(specialty_ids) == 0:
             logger.warning("Search without specialty_ids")
             return jsonify({'success': False, 'error': 'Specjalność jest obowiązkowa'}), 400

        logger.debug(f"Search params: {data}")
        results = med_app.search_appointments(
            user_email=user_email,
            profile=data.get('profile'),
            specialty_ids=data.get('specialty_ids'),
            doctor_ids=data.get('doctor_ids'),
            clinic_ids=data.get('clinic_ids'),
            preferred_days=data.get('preferred_days', []),
            time_range=data.get('time_range'),
            day_time_ranges=data.get('day_time_ranges', {}),
            excluded_dates=data.get('excluded_dates', []),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            min_lead_time=data.get('min_lead_time'), # Pass new param
            headless=True
        )
        logger.info(f"Search completed: {len(results)} results")
        return jsonify({'success': True, 'count': len(results), 'data': results}), 200
    except Exception as e: 
        logger.error(f"Error searching appointments: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/appointments/book', methods=['POST'])
@require_login
def book_appointment():
    if not med_app: return jsonify({'success': False, 'error': 'App not init'}), 500
    user_email = get_current_user_email()
    logger.info(f"Book appointment request from {user_email}")
    try:
        data = request.get_json() or {}
        result = med_app.book_appointment(
            user_email=user_email,
            profile=data.get('profile'), 
            appointment_id=data.get('appointment_id'),
            booking_string=data.get('booking_string') or data.get('bookingString')
        )
        logger.info(f"Booking result: {result.get('success')}")
        return jsonify(result), 200
    except Exception as e: 
        logger.error(f"Error booking appointment: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ======== SERVING FRONTEND =========

@app.route('/')
def index():
    logger.debug("Serving index.html")
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/') or path.startswith('auth/'):
        return jsonify({'error': 'Not found'}), 404
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    if not med_app: 
        logger.error("❌ Global init failed - med_app is None")
    else:
        logger.info("✅ All systems initialized")
    
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Flask on 0.0.0.0:{port}")
    logger.info("=" * 80)
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG')=='True', threaded=True)
