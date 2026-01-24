"""
Dedykowana warstwa API dla Medicover - ZREFAKTORYZOWANA
Eliminuje duplikację walidacji Bearer Token i obsługi błędów
Używa centralnych funkcji z error_handler.py
"""

import requests
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from .error_handler import (
    handle_api_errors, 
    log_api_call, 
    validate_bearer_token,
    AuthenticationException,
    MedicoverAPIException,
    RateLimitException
)

logger = logging.getLogger(__name__)

class TimeoutConfig:
    """Konfiguracja timeoutów dla różnych operacji"""
    SELENIUM_WAIT = 15
    SELENIUM_WAIT_VISIBLE = 10
    SELENIUM_WAIT_HEADLESS = 15
    API_TIMEOUT = 30
    LOGIN_TIMEOUT = 60
    PAGE_LOAD_TIMEOUT = 30
    SESSION_TIMEOUT = 3600  # 1 godzina
    TOKEN_EXPIRY_BUFFER = 300  # 5 minut przed wygaśnięciem

class MedicoverAPI:
    """
    Klasa do obsługi API Medicover z centralną obsługą błędów
    USUNIĘTE: duplikaty walidacji tokenów i obsługi błędów
    """
    
    BASE_URL = "https://api-gateway-online24.medicover.pl"
    APPOINTMENTS_ENDPOINT = "/appointments/api/search-appointments/slots"
    BOOKING_ENDPOINT = "/appointments/api/search-appointments/book-appointment"
    FILTERS_ENDPOINT = "/service-selector-configurator/api/search-appointments/filters"
    
    def __init__(self, bearer_token: Optional[str] = None):
        self.bearer_token = None
        self.session = requests.Session()
        self._setup_session()
        
        if bearer_token:
            self.set_bearer_token(bearer_token)
    
    def _setup_session(self) -> None:
        """Konfiguruje sesję requests z nagłówkami zgodnie z HAR"""
        headers = {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept-Language": "pl,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Origin": "https://online24.medicover.pl",
            "Referer": "https://online24.medicover.pl/",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=0",
            "DNT": "1"
        }
        self.session.headers.update(headers)
        logger.debug("Session configured with HAR-compliant headers")
    
    def set_bearer_token(self, token: str) -> bool:
        """
        ZREFAKTORYZOWANE: Używa validate_bearer_token() z error_handler
        Usuwa duplikację walidacji
        """
        if not token:
            logger.error("Empty Bearer token provided")
            return False
        
        token = token.strip()
        
        # KLUCZOWA ZMIANA: używamy funkcji z error_handler.py
        if not validate_bearer_token(token):
            logger.error("Bearer token validation failed")
            return False
        
        self.bearer_token = token
        self.session.headers["Authorization"] = f"Bearer {token}"
        
        logger.info(f"Bearer token set successfully (length: {len(token)})")
        logger.debug(f"Token prefix: {token[:50]}...")
        return True
    
    def clear_token(self) -> None:
        """Czyści token autoryzacji"""
        self.bearer_token = None
        
        # Usuń oba możliwe warianty nagłówka
        for header_name in ["Authorization", "authorization"]:
            if header_name in self.session.headers:
                del self.session.headers[header_name]
        
        logger.debug("Bearer token cleared")

# --- Wklej ten kod w miejsce starej metody _build_request_params w medicover_api.py ---

    def _build_request_params(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Buduje i tłumaczy parametry na format zrozumiały dla API Medicover.
        Wersja finalna: poprawnie tłumaczy wszystkie znane warianty kluczy
        i przekazuje pozostałe parametry bez zmian.
        """
        final_api_params = {}
        # Pracujemy na kopii, aby nie modyfikować oryginalnego słownika
        internal_params = search_params.copy()

        # --- Tłumaczenie znanych parametrów ---
        # Używamy .pop(key, None) aby bezpiecznie usunąć klucz po przetworzeniu.
        # Ta struktura poprawnie obsługuje zarówno nazwy z podkreśleniami, jak i CamelCase.

        if 'region_ids' in internal_params or 'RegionIds' in internal_params:
            ids = internal_params.pop('region_ids', internal_params.pop('RegionIds', []))
            final_api_params['RegionIds'] = ids

        if 'specialty_ids' in internal_params or 'SpecialtyIds' in internal_params:
            ids = internal_params.pop('specialty_ids', internal_params.pop('SpecialtyIds', []))
            final_api_params['SpecialtyIds'] = ids

        if 'clinic_ids' in internal_params or 'ClinicIds' in internal_params:
            ids = internal_params.pop('clinic_ids', internal_params.pop('ClinicIds', []))
            final_api_params['ClinicIds'] = ids

        if 'doctor_ids' in internal_params or 'DoctorIds' in internal_params:
            ids = internal_params.pop('doctor_ids', internal_params.pop('DoctorIds', []))
            final_api_params['DoctorIds'] = ids

        if 'page' in internal_params:
            final_api_params['Page'] = internal_params.pop('page')
        
        if 'page_size' in internal_params:
            final_api_params['PageSize'] = internal_params.pop('page_size')
        
        if 'slot_search_type' in internal_params:
            final_api_params['SlotSearchType'] = internal_params.pop('slot_search_type')
        
        if 'is_overbooking_search_disabled' in internal_params:
            val = internal_params.pop('is_overbooking_search_disabled')
            final_api_params['isOverbookingSearchDisabled'] = str(val).lower()

        # --- Scalanie pozostałych parametrów ---
        # Wszystko, co zostało w `internal_params`, to parametry już w poprawnym
        # formacie (np. 'StartTime'), które zostały dodane w GUI.
        final_api_params.update(internal_params)

        # --- Ostateczna walidacja i domyślna data ---
        if 'StartTime' not in final_api_params:
            final_api_params['StartTime'] = datetime.now().strftime("%Y-%m-%d")
        
        logger.debug(f"Zbudowano finalne parametry zapytania do API: {final_api_params}")
        return final_api_params
        
    @handle_api_errors  # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    @log_api_call       # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    def search_appointments(self, search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ZREFAKTORYZOWANE: Wyszukuje wizyty przez API
        Usunięta ręczna obsługa błędów - zastąpiona dekoratorami
        """
        if not self.bearer_token:
            raise ValueError("Bearer token required for appointment search")
        
        url = f"{self.BASE_URL}{self.APPOINTMENTS_ENDPOINT}"
        params = self._build_request_params(search_params)
        
        logger.info("Searching appointments via API...")
        logger.debug(f"Request URL: {url}")
        logger.debug(f"Request params: {params}")
        
        response = self.session.get(
            url, 
            params=params, 
            timeout=TimeoutConfig.API_TIMEOUT
        )       

        if response.status_code == 401:
            logger.error("API returned status 401 - Bearer token expired or invalid")
            logger.error(f"Response body: {response.text}")
            self.clear_token()
            raise AuthenticationException("Bearer token expired - re-authentication required")
        elif response.status_code == 429:
            logger.warning("API returned status 429 - Rate limit exceeded.")
            raise RateLimitException("Too many requests to Medicover API.")
        return self._process_response(response)
    
    def _process_response(self, response: requests.Response) -> List[Dict[str, Any]]:
        """Przetwarza odpowiedź API"""
        logger.info(f"API Response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"API returned status: {response.status_code}")
            logger.debug(f"Response content: {response.text[:500]}")
            return []
        
        # Sprawdź Content-Type
        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            logger.error(f"Non-JSON response: {content_type}")
            return []
        
        # Sprawdź czy response nie jest pusty
        if not response.text.strip():
            logger.error("Empty response from API")
            return []
        
        try:
            data = response.json()
            if not isinstance(data, dict):
                logger.error(f"Unexpected response format: {type(data)}")
                return []
            
            # Wyciągnij appointments z różnych możliwych kluczy
            appointments = data.get("items", data.get("slots", data.get("appointments", [])))
            
            if not isinstance(appointments, list):
                logger.error(f"Appointments data is not a list: {type(appointments)}")
                return []
            
            logger.info(f"Found {len(appointments)} appointments")
            
            # Loguj dodatkowe informacje z response
            if logger.isEnabledFor(logging.DEBUG):
                total_count = data.get("count", data.get("totalCount", 0))
                page = data.get("page", data.get("pageNumber", 1))
                logger.debug(f"Response metadata: count={total_count}, page={page}")
            
            return appointments
            
        except ValueError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.debug(f"Raw response: {response.text[:1000]}")
            return []
    
    @handle_api_errors  # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    @log_api_call       # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    def get_filters(self, region_id: Optional[int] = None) -> Dict[str, Any]:
        """Pobiera filtry przez API"""
        if not self.bearer_token:
            raise ValueError("Bearer token required for filters")
        
        url = f"{self.BASE_URL}{self.FILTERS_ENDPOINT}"
        params = {}
        if region_id:
            params["RegionId"] = region_id
        
        logger.info("Fetching filters via API...")
        
        response = self.session.get(
            url, 
            params=params, 
            timeout=TimeoutConfig.API_TIMEOUT
        )
        
        if response.status_code != 200:
            logger.error(f"Filters API returned status: {response.status_code}")
            return {}
        
        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            logger.error(f"Filters returned non-JSON: {content_type}")
            return {}
        
        filters = response.json()
        logger.info("Filters fetched successfully")
        return filters
    
    @handle_api_errors  # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    @log_api_call       # ZREFAKTORYZOWANE: używamy dekoratora z error_handler
    def book_appointment(self, booking_string: str, metadata: Dict[str, str] = None) -> Dict[str, Any]:
        """Rezerwuje wizytę używając bookingString"""
        if not self.bearer_token:
            raise ValueError("Bearer token required for appointment booking")
        
        if not booking_string:
            raise ValueError("Booking string is required for reservation")
        
        if not metadata:
            metadata = {"appointmentSource": "Direct"}
        
        url = f"{self.BASE_URL}{self.BOOKING_ENDPOINT}"
        payload = {
            "bookingString": booking_string,
            "metadata": metadata
        }
        
        logger.info(f"Booking appointment with bookingString: {booking_string[:50]}...")
        logger.debug(f"Request URL: {url}")
        logger.debug(f"Request payload: {payload}")
        
        headers = {"Content-Type": "application/json"}
        
        response = self.session.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=TimeoutConfig.API_TIMEOUT
        )
        
        # Sprawdź status odpowiedzi
        if response.status_code == 200:
            result = response.json()
            appointment_id = result.get("appointmentId")
            logger.info(f"Appointment booked successfully - ID: {appointment_id}")
            return {
                "success": True,
                "appointmentId": appointment_id,
                "message": "Wizyta została pomyślnie zarezerwowana"
            }
        elif response.status_code == 400:
            logger.error("Bad request - booking string may be invalid or slot unavailable")
            return {
                "success": False,
                "error": "badrequest",
                "message": "Slot niedostępny lub nieprawidłowy identyfikator wizyty"
            }
        elif response.status_code == 401:
            logger.error("Authentication failed - Bearer token expired")
            raise AuthenticationException("Bearer token expired - re-authentication required")
        elif response.status_code == 409:
            logger.error("Conflict - slot already booked")
            return {
                "success": False,
                "error": "slottaken",
                "message": "Brak możliwości zarezerwowania tego typu wizyty"
            }
        else:
            logger.error(f"Booking failed with status: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return {
                "success": False,
                "error": "apierror",
                "message": f"Błąd serwera: {response.status_code}"
            }
    
    def test_connection(self) -> bool:
        """Testuje połączenie z API"""
        if not self.bearer_token:
            logger.debug("No Bearer token for connection test")
            return False
        
        try:
            test_params = {
                "Page": 1,
                "PageSize": 1,
                "SlotSearchType": "Standard",
                "RegionIds": [204],
                "StartTime": datetime.now().strftime("%Y-%m-%d"),
                "isOverbookingSearchDisabled": "false"
            }
            
            url = f"{self.BASE_URL}{self.APPOINTMENTS_ENDPOINT}"
            response = self.session.get(url, params=test_params, timeout=10)
            
            # 400 może być OK dla test call
            is_connected = response.status_code in [200, 400, 403]
            logger.debug(f"Connection test result: {response.status_code} - {'OK' if is_connected else 'FAIL'}")
            return is_connected
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False
    
    def get_session_info(self) -> Dict[str, Any]:
        """Zwraca informacje o sesji API"""
        return {
            "base_url": self.BASE_URL,
            "has_token": bool(self.bearer_token),
            "token_length": len(self.bearer_token) if self.bearer_token else 0,
            "token_prefix": f"{self.bearer_token[:20]}..." if self.bearer_token else None,
            "api_ready": bool(self.bearer_token),
            "headers_count": len(self.session.headers),
            "has_auth_header": "Authorization" in self.session.headers
        }
