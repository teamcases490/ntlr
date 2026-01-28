"""
Utility functions for the geocoding pipeline.
"""
import time
import re
from functools import wraps
from typing import Callable, Any, Optional, Tuple
import requests
from .config import Config
from .models import NetworkException, APIException, ErrorType
from .logger import Logger

logger = Logger.get_logger(__name__)


def retry_with_backoff(max_retries: Optional[int] = None, 
                       delay: Optional[float] = None,
                       backoff: Optional[float] = None):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for exponential delay
    """
    max_retries = max_retries or Config.MAX_RETRIES
    delay = delay or Config.RETRY_DELAY
    backoff = backoff or Config.RETRY_BACKOFF
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.RequestException, NetworkException) as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}. "
                            f"Retrying in {current_delay:.1f}s... Error: {str(e)}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}")
                except Exception as e:
                    # Don't retry on non-network errors
                    logger.error(f"Non-retryable error in {func.__name__}: {str(e)}")
                    raise
            
            # If we get here, all retries failed
            raise NetworkException(f"Failed after {max_retries + 1} attempts: {str(last_exception)}")
        
        return wrapper
    return decorator


def sanitize_input(text: str) -> str:
    """
    Sanitize user input text.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove potentially harmful characters but keep Unicode for Indian languages
    # Only remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
    
    return text


def validate_coordinates(lat: float, lon: float) -> Tuple[bool, Optional[str]]:
    """
    Validate latitude and longitude coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check basic validity
    if not (-90 <= lat <= 90):
        return False, f"Invalid latitude: {lat}. Must be between -90 and 90."
    
    if not (-180 <= lon <= 180):
        return False, f"Invalid longitude: {lon}. Must be between -180 and 180."
    
    # Check if within India bounds
    if not Config.is_within_india(lat, lon):
        return False, f"Coordinates ({lat}, {lon}) are outside India bounds."
    
    return True, None


def parse_address_components(components: list) -> dict:
    """
    Parse Google Maps address components into structured format.
    
    Args:
        components: List of address component dictionaries from Google API
        
    Returns:
        Dictionary with parsed components
    """
    result = {
        'street': None,
        'locality': None,
        'city': None,
        'state': None,
        'postal_code': None,
        'country': None
    }
    
    for component in components:
        types = component.get('types', [])
        long_name = component.get('long_name', '')
        
        if 'route' in types or 'street_address' in types:
            result['street'] = long_name
        elif 'sublocality' in types or 'sublocality_level_1' in types:
            result['locality'] = long_name
        elif 'locality' in types:
            result['city'] = long_name
        elif 'administrative_area_level_1' in types:
            result['state'] = long_name
        elif 'postal_code' in types:
            result['postal_code'] = long_name
        elif 'country' in types:
            result['country'] = long_name
    
    return result


def calculate_quality_score(location_type: str, 
                           has_postal_code: bool,
                           is_in_india: bool,
                           validation_confidence: float = 0.0) -> float:
    """
    Calculate overall quality score for a geocoded location.
    
    Args:
        location_type: Google's location_type (ROOFTOP, etc.)
        has_postal_code: Whether postal code is available
        is_in_india: Whether location is within India bounds
        validation_confidence: Confidence from address validation (0-1)
        
    Returns:
        Quality score between 0 and 1
    """
    score = 0.0
    
    # Location type score (40%)
    location_scores = {
        'ROOFTOP': 1.0,
        'RANGE_INTERPOLATED': 0.8,
        'GEOMETRIC_CENTER': 0.6,
        'APPROXIMATE': 0.4
    }
    score += location_scores.get(location_type, 0.3) * 0.4
    
    # Postal code availability (20%)
    if has_postal_code:
        score += 0.2
    
    # India bounds check (20%)
    if is_in_india:
        score += 0.2
    
    # Validation confidence (20%)
    score += validation_confidence * 0.2
    
    return min(score, 1.0)


def format_error_message(error: Exception, context: str = "") -> str:
    """
    Format error message for user-friendly display.
    
    Args:
        error: Exception object
        context: Additional context about the error
        
    Returns:
        Formatted error message
    """
    error_type = type(error).__name__
    error_msg = str(error)
    
    if context:
        return f"{context}: {error_type} - {error_msg}"
    return f"{error_type}: {error_msg}"


def extract_place_id_from_autocomplete(prediction: dict) -> Optional[str]:
    """
    Extract place_id from autocomplete prediction.
    
    Args:
        prediction: Autocomplete prediction dictionary
        
    Returns:
        Place ID or None
    """
    return prediction.get('place_id')


def is_valid_input(text: str, min_length: int = 2, max_length: int = 500) -> Tuple[bool, Optional[str]]:
    """
    Validate input text.
    
    Args:
        text: Input text to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not text:
        return False, "Input text is empty"
    
    text = text.strip()
    
    if len(text) < min_length:
        return False, f"Input too short. Minimum {min_length} characters required."
    
    if len(text) > max_length:
        return False, f"Input too long. Maximum {max_length} characters allowed."
    
    return True, None


def make_api_request(url: str, params: Optional[dict] = None, 
                     json_data: Optional[dict] = None,
                     method: str = 'GET') -> dict:
    """
    Make an API request with error handling.
    
    Args:
        url: API endpoint URL
        params: Query parameters
        json_data: JSON payload for POST requests
        method: HTTP method (GET or POST)
        
    Returns:
        Response JSON
        
    Raises:
        NetworkException: On network errors
        APIException: On API errors
    """
    try:
        if method.upper() == 'POST':
            # Add API key to URL for POST requests
            url_with_key = f"{url}?key={Config.GOOGLE_API_KEY}"
            response = requests.post(
                url_with_key,
                json=json_data,
                timeout=Config.REQUEST_TIMEOUT
            )
        else:
            response = requests.get(
                url,
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.Timeout:
        raise NetworkException(f"Request timeout after {Config.REQUEST_TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        raise NetworkException(f"Connection error: {str(e)}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else None
        raise APIException(f"HTTP error: {str(e)}", status_code)
    except requests.exceptions.RequestException as e:
        raise NetworkException(f"Request failed: {str(e)}")
    except ValueError as e:
        raise APIException(f"Invalid JSON response: {str(e)}")
