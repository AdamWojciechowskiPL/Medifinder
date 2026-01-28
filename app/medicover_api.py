"""
Dedykowana warstwa API dla Medicover - ZREFAKTORYZOWANA (STATELESS TOKEN)
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
    Klasa do obsługi API Medicover.
    ZMIANA: Stateless - token jest przekazywany w każdym żądaniu, nie trzymany w stanie.
    """
    
    BASE_URL = "https://api-gateway-online24.medicover.pl"
    APPOINTMENTS_ENDPOINT = "/appointments/api/search-appointments/slots"
    BOOKING_ENDPOINT = "/appointments/api/search-appointments/book-appointment"
    FILTERS_ENDPOINT = "/service-selector-configurator/api/search-appointments/filters"
    DEFAULT_REGION_ID = 204 # Warszawa jako domyślny region
    
    def __init__(self):
        self.session = requests.Session()
        self._setup_session()
    
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
    
    # Metoda set_bearer_token usunięta - token przekazywany per request
    
    def clear_token(self) -> None:
        """Helper backward-compatibility (no-op now)"""
        pass

    def _build_request_params(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Buduje i tłumaczy parametry na format zrozumiały dla API Medicover.
        """
        final_api_params = {}
        internal_params = search_params.copy()

        # Usuwamy profile_id jeśli istnieje, bo to parametr wewnętrzny
        internal_params.pop('profile_id', None)

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

        final_api_params.update(internal_params)

        if 'StartTime' not in final_api_params:
            final_api_params['StartTime'] = datetime.now().strftime("%Y-%m-%d")
        
        if 'RegionIds' not in final_api_params or not final_api_params['RegionIds']:
             final_api_params['RegionIds'] = [self.DEFAULT_REGION_ID]

        return final_api_params
        
    @handle_api_errors
    @log_api_call
    def search_appointments(self, search_params: Dict[str, Any], token: str) -> List[Dict[str, Any]]:
        """
        Wyszukuje wizyty przez API.
        Wymaga podania tokenu explicitnie.
        """
        if not token:
            raise ValueError("Bearer token required for appointment search")
        
        url = f"{self.BASE_URL}{self.APPOINTMENTS_ENDPOINT}"
        params = self._build_request_params(search_params)
        
        # Przygotuj nagłówki dla tego konkretnego zapytania
        headers = {"Authorization": f"Bearer {token}"}
        
        response = self.session.get(
            url, 
            params=params, 
            headers=headers, # Merge z session headers
            timeout=TimeoutConfig.API_TIMEOUT
        )       

        if response.status_code == 401:
            logger.error("API returned status 401 - Bearer token expired or invalid")
            raise AuthenticationException("Bearer token expired - re-authentication required")
        elif response.status_code == 429:
            logger.warning("API returned status 429 - Rate limit exceeded.")
            raise RateLimitException("Too many requests to Medicover API.")
        return self._process_response(response)
    
    def _process_response(self, response: requests.Response) -> List[Dict[str, Any]]:
        if response.status_code != 200:
            logger.error(f"API returned status: {response.status_code}")
            return []
        
        try:
            data = response.json()
            appointments = data.get("items", data.get("slots", data.get("appointments", [])))
            return appointments
        except ValueError:
            return []
    
    @handle_api_errors
    @log_api_call
    def get_filters(self, token: str, region_id: Optional[int] = None) -> Dict[str, Any]:
        if not token:
            raise ValueError("Bearer token required for filters")
        
        url = f"{self.BASE_URL}{self.FILTERS_ENDPOINT}"
        params = {}
        if region_id:
            params["RegionId"] = region_id
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = self.session.get(
            url, 
            params=params,
            headers=headers,
            timeout=TimeoutConfig.API_TIMEOUT
        )
        
        if response.status_code != 200:
            return {}
        
        return response.json()
    
    @handle_api_errors
    @log_api_call
    def book_appointment(self, booking_string: str, token: str, metadata: Dict[str, str] = None) -> Dict[str, Any]:
        if not token:
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
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = self.session.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=TimeoutConfig.API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "appointmentId": result.get("appointmentId"),
                "message": "Wizyta została pomyślnie zarezerwowana"
            }
        elif response.status_code == 400:
            return {"success": False, "error": "badrequest", "message": "Slot niedostępny"}
        elif response.status_code == 401:
            raise AuthenticationException("Bearer token expired")
        elif response.status_code == 409:
            return {"success": False, "error": "slottaken", "message": "Masz już rezerwację u tej specjalności!"}
        else:
            return {"success": False, "error": "apierror", "message": f"Błąd serwera: {response.status_code}"}

    def get_session_info(self) -> Dict[str, Any]:
        return {
            "base_url": self.BASE_URL,
            "is_stateless": True,
            "headers_count": len(self.session.headers)
        }