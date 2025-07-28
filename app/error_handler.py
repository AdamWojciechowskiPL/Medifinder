"""
Centralna obsługa błędów API z uproszczoną walidacją Bearer Token
Zastępuje zduplikowaną logikę obsługi błędów w różnych metodach
"""

import requests
import functools
import time
import logging
from functools import wraps
from typing import Callable, Any, Optional, Dict

logger = logging.getLogger(__name__)

class RetryConfig:
    """Konfiguracja ponawiania operacji"""
    MAX_LOGIN_ATTEMPTS = 3
    MAX_API_RETRIES = 3
    MAX_BOOKING_RETRIES = 2
    RETRY_DELAY_BASE = 2  # sekundy
    RETRY_EXPONENTIAL_BACKOFF = True
    TOKEN_REFRESH_INTERVAL = 50  # minuty
    
    # Kody błędów do ponowienia
    RETRYABLE_HTTP_CODES = [429, 502, 503, 504]
    RETRYABLE_EXCEPTIONS = [
        'ConnectionError',
        'Timeout',
        'HTTPError'
    ]

class MedicoverAPIException(Exception):
    """Bazowy wyjątek dla błędów API Medicover"""
    pass

class AuthenticationException(MedicoverAPIException):
    """Wyjątek dla błędów autoryzacji"""
    pass

class ForbiddenException(MedicoverAPIException):
    """Wyjątek dla błędów uprawnień"""
    pass

class TimeoutException(MedicoverAPIException):
    """Wyjątek dla błędów timeout"""
    pass

class RateLimitException(MedicoverAPIException):
    """Wyjątek dla przekroczenia limitów API"""
    pass
    
class APIRetryExhaustedError(MedicoverAPIException):
    """Wyjątek dla wyczerpania prób ponowienia zapytania API."""
    pass

def handle_api_errors(func=None, *, max_retries: int = RetryConfig.MAX_API_RETRIES, delay: float = RetryConfig.RETRY_DELAY_BASE):
    """
    Dekorator obsługi błędów API.
    - Ponawia próby dla błędów połączenia.
    - Natychmiast przerywa i przekazuje dalej błąd 429 (Rate Limit).
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return f(*args, **kwargs)
                
                # NOWA LOGIKA: Błąd 429 jest traktowany specjalnie
                except RateLimitException:
                    # Nie ponawiaj, od razu rzuć wyjątek wyżej
                    raise
                
                # Stara logika dla innych błędów połączenia
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt >= max_retries:
                        logger.error(f"API call failed on the last attempt ({attempt + 1}).")
                        break

                    wait_time = delay * (2 ** attempt)
                    logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                
                except AuthenticationException:
                    raise

                except Exception as e:
                    raise
            
            if last_exception:
                logger.error("All API retry attempts failed due to a connection error.")
                raise MedicoverAPIException("Błąd połączenia z API po wielu próbach.") from last_exception
                    
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)

def handle_response_status(response: requests.Response, function_name: str, attempt: int) -> requests.Response:
    """Obsługuje kody statusów HTTP odpowiedzi"""
    if response.status_code == 200:
        return response
    elif response.status_code == 401:
        logger.error(f"Authentication failed in {function_name} (attempt {attempt + 1})")
        # Nie loguj jako błąd krytyczny - to może być normalny expired token
        raise AuthenticationException(
            f"Bearer token expired or invalid in {function_name}. Status: {response.status_code}"
        )
    elif response.status_code == 403:
        logger.error(f"Access forbidden in {function_name} (attempt {attempt + 1})")
        raise ForbiddenException(
            f"Access denied in {function_name}. Status: {response.status_code}"
        )

    elif response.status_code == 429:
        logger.warning(f"Rate limit exceeded in {function_name} (attempt {attempt + 1})")
        raise RateLimitException(
            f"Too many requests in {function_name}. Status: {response.status_code}"
        )
    
    elif response.status_code >= 500:
        logger.error(f"Server error in {function_name} (attempt {attempt + 1}): {response.status_code}")
        raise MedicoverAPIException(
            f"Server error in {function_name}. Status: {response.status_code}"
        )
    
    else:
        logger.warning(f"Unexpected status in {function_name}: {response.status_code}")
        raise MedicoverAPIException(
            f"Unexpected status in {function_name}: {response.status_code}"
        )

def log_api_call(func: Callable) -> Callable:
    """Dekorator do logowania wywołań API"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Starting API call: {func.__name__}")
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"API call {func.__name__} completed in {execution_time:.2f}s")
            return result
        
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"API call {func.__name__} failed after {execution_time:.2f}s: {str(e)}")
            raise
    
    return wrapper

def validate_bearer_token(token: Optional[str]) -> bool:
    """
    Uproszczona walidacja Bearer token - kompatybilna z Medicover
    Usunięto skomplikowaną walidację JWT która odrzucała prawidłowe tokeny
    """
    if not token:
        logger.debug("Token validation failed: empty token")
        return False
    
    # Usuń prefix "Bearer " jeśli istnieje
    actual_token = token.replace('Bearer ', '') if token.startswith('Bearer ') else token
    
    # Prosta walidacja długości - jak w działającej monolitycznej wersji
    if len(actual_token) < 50:
        logger.debug(f"Token validation failed: too short ({len(actual_token)} chars)")
        return False
    
    # Podstawowe sprawdzenie czy zawiera typowe znaki tokenu
    if not any(c in actual_token for c in '.=-_'):
        logger.debug("Token validation failed: missing typical token characters")
        return False
    
    logger.debug(f"Token validation successful: {len(actual_token)} chars")
    return True

class APIErrorReporter:
    """Klasa do raportowania i analizowania błędów API"""
    
    def __init__(self):
        self.error_counts = {
            'auth_errors': 0,
            'timeout_errors': 0,
            'forbidden_errors': 0,
            'server_errors': 0,
            'other_errors': 0
        }
        self.last_errors = []
    
    def report_error(self, error: Exception):
        """Raportuje błąd i aktualizuje statystyki"""
        if isinstance(error, AuthenticationException):
            self.error_counts['auth_errors'] += 1
        elif isinstance(error, TimeoutException):
            self.error_counts['timeout_errors'] += 1
        elif isinstance(error, ForbiddenException):
            self.error_counts['forbidden_errors'] += 1
        elif 'server error' in str(error).lower():
            self.error_counts['server_errors'] += 1
        else:
            self.error_counts['other_errors'] += 1
        
        # Przechowywanie ostatnich błędów (maksymalnie 10)
        self.last_errors.append({
            'timestamp': time.time(),
            'error_type': type(error).__name__,
            'message': str(error)
        })
        
        if len(self.last_errors) > 10:
            self.last_errors.pop(0)
    
    def get_error_summary(self) -> dict:
        """Zwraca podsumowanie błędów"""
        total_errors = sum(self.error_counts.values())
        return {
            'total_errors': total_errors,
            'error_breakdown': self.error_counts.copy(),
            'recent_errors': self.last_errors.copy()
        }
