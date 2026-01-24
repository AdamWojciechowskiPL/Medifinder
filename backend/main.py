import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# Konfiguracja ścieżek
ROOT_DIR = Path(__file__).parent.resolve()
APP_DIR = ROOT_DIR / "app"
CONFIG_DIR = ROOT_DIR / "config"

# Upewniamy się, że katalogi istnieją
APP_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# Dodajemy katalog 'app' do ścieżki Pythona
sys.path.insert(0, str(APP_DIR))

# Konfiguracja loggingu
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicjalizacja Flask
app = Flask(__name__)
CORS(app)

# Ustawienia
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max request

# Globalna instancja aplikacji Medifinder
med_app = None

try:
    from main_app import MedicoverApp
    from gui import MedicoverGUI
except ImportError as e:
    logger.error(f"Nie można zaimportować modułów aplikacji: {e}")
    logger.info("Upewnij się, że katalog 'app' zawiera main.py i gui.py")


def init_app():
    """Inicjalizacja aplikacji Medifinder"""
    global med_app
    try:
        med_app = MedicoverApp(CONFIG_DIR)
        logger.info("✅ Aplikacja Medifinder zainicjalizowana pomyślnie")
        return True
    except Exception as e:
        logger.error(f"❌ Błąd podczas inicjalizacji aplikacji: {e}")
        return False


# ============ HEALTH CHECK ============
@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint do sprawdzenia statusu aplikacji"""
    return jsonify({
        'status': 'ok',
        'service': 'Medifinder API',
        'version': '1.0.0'
    }), 200


# ============ PROFILES ============
@app.route('/api/v1/profiles', methods=['GET'])
def get_profiles():
    """Pobiera listę dostępnych profili użytkownika"""
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    
    try:
        profiles = med_app.get_available_profiles()
        return jsonify({
            'success': True,
            'data': profiles,
            'count': len(profiles)
        }), 200
    except Exception as e:
        logger.error(f"Błąd przy pobieraniu profili: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/profiles/add', methods=['POST'])
def add_profile():
    """Dodaje nowy profil użytkownika"""
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    
    try:
        data = request.get_json()
        required_fields = ['login', 'password', 'name']
        
        if not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'error': f'Brakuje pól: {required_fields}'
            }), 400
        
        result = med_app.add_profile(
            login=data['login'],
            password=data['password'],
            name=data['name']
        )
        
        return jsonify({
            'success': True,
            'message': f'Profil "{data["name"]}" dodany pomyślnie',
            'data': result
        }), 201
    except Exception as e:
        logger.error(f"Błąd przy dodawaniu profilu: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ APPOINTMENTS ============
@app.route('/api/v1/appointments/search', methods=['POST'])
def search_appointments():
    """Wyszukuje dostępne wizyty"""
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    
    try:
        data = request.get_json()
        
        # Walidacja wymaganych pól
        if 'profile' not in data:
            return jsonify({'success': False, 'error': 'Wymagane pole: profile'}), 400
        
        # Parametry wyszukiwania
        search_params = {
            'profile': data.get('profile'),
            'specialty': data.get('specialty', ''),
            'doctors': data.get('doctors', []),  # Lista
            'clinics': data.get('clinics', []),  # Lista
            'preferred_days': data.get('preferred_days', []),  # Lista (1-7)
            'time_range': data.get('time_range', {'start': '00:00', 'end': '23:59'}),
            'headless': True
        }
        
        logger.info(f"🔍 Wyszukiwanie wizyt z parametrami: {search_params}")
        
        results = med_app.search_appointments(**search_params)
        
        return jsonify({
            'success': True,
            'count': len(results),
            'data': results
        }), 200
    except Exception as e:
        logger.error(f"Błąd przy wyszukiwaniu wizyt: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/appointments/book', methods=['POST'])
def book_appointment():
    """Rezerwuje wybraną wizytę"""
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    
    try:
        data = request.get_json()
        
        required_fields = ['profile', 'appointment_id']
        if not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'error': f'Brakuje pól: {required_fields}'
            }), 400
        
        logger.info(f"📅 Rezerwacja wizyty: {data['appointment_id']} dla profilu: {data['profile']}")
        
        result = med_app.book_appointment(
            profile=data['profile'],
            appointment_id=data['appointment_id']
        )
        
        return jsonify({
            'success': True,
            'message': 'Wizyta zarezerwowana pomyślnie',
            'data': result
        }), 200
    except Exception as e:
        logger.error(f"Błąd przy rezerwacji wizyty: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/appointments/auto-book', methods=['POST'])
def auto_book_appointment():
    """Uruchamia automatyczną rezerwację z kryteriami"""
    if not med_app:
        return jsonify({'success': False, 'error': 'Aplikacja nie zainicjalizowana'}), 500
    
    try:
        data = request.get_json()
        
        required_fields = ['profile', 'specialty']
        if not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'error': f'Brakuje pól: {required_fields}'
            }), 400
        
        auto_params = {
            'profile': data['profile'],
            'specialty': data['specialty'],
            'doctors': data.get('doctors', []),
            'clinics': data.get('clinics', []),
            'preferred_days': data.get('preferred_days', [1, 2, 3, 4, 5]),
            'time_range': data.get('time_range', {'start': '08:00', 'end': '20:00'}),
            'auto_book': True,
            'headless': True
        }
        
        logger.info(f"🤖 Automatyczna rezerwacja z parametrami: {auto_params}")
        
        result = med_app.auto_book_appointment(**auto_params)
        
        return jsonify({
            'success': True,
            'message': 'Automatyczna rezerwacja uruchomiona',
            'data': result
        }), 200
    except Exception as e:
        logger.error(f"Błąd przy automatycznej rezerwacji: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ ERROR HANDLERS ============
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint nie znaleziony'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Wewnętrzny błąd serwera: {error}")
    return jsonify({'success': False, 'error': 'Wewnętrzny błąd serwera'}), 500


@app.errorhandler(400)
def bad_request(error):
    return jsonify({'success': False, 'error': 'Nieprawidłowe żądanie'}), 400


if __name__ == '__main__':
    # Inicjalizacja aplikacji
    if not init_app():
        logger.error("Nie można było zainicjalizować aplikacji")
        sys.exit(1)
    
    # Pobranie portu z zmiennych środowiskowych (Railway ustawia PORT)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    
    logger.info(f"🚀 Uruchamianie serwera na porcie {port}")
    logger.info(f"🌐 API dostępne na: http://0.0.0.0:{port}/api/v1")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )
