"""
Google Places Autocomplete API integration.
"""
from typing import List, Optional, Dict, Any
from .config import Config
from .models import AutocompleteResult, InvalidInputException
from .utils import (
    retry_with_backoff, sanitize_input, is_valid_input, 
    make_api_request
)
from .cache_manager import get_cache_manager
from .logger import Logger

logger = Logger.get_logger(__name__)


class AutocompleteService:
    """Service for Google Places Autocomplete API."""
    
    def __init__(self, use_cache: bool = True):
        """
        Initialize autocomplete service.
        
        Args:
            use_cache: Whether to use caching
        """
        self.use_cache = use_cache
        self.cache = get_cache_manager() if use_cache else None
    
    @retry_with_backoff()
    def get_predictions(self, 
                       input_text: str,
                       location: Optional[str] = None,
                       radius: Optional[int] = None,
                       language: Optional[str] = None) -> AutocompleteResult:
        """
        Get place predictions for input text.
        
        Args:
            input_text: User input text
            location: Optional location bias (lat,lng format)
            radius: Optional radius in meters for location bias
            language: Optional language code (default: 'en')
            
        Returns:
            AutocompleteResult with predictions
            
        Raises:
            InvalidInputException: If input is invalid
        """
        # Sanitize and validate input
        input_text = sanitize_input(input_text)
        is_valid, error_msg = is_valid_input(input_text)
        if not is_valid:
            logger.warning(f"Invalid autocomplete input: {error_msg}")
            raise InvalidInputException(error_msg)
        
        logger.info(f"Autocomplete request: '{input_text[:50]}...'")
        
        # Check cache
        cache_key = {
            'service': 'autocomplete',
            'input': input_text,
            'location': location,
            'radius': radius,
            'language': language
        }
        
        if self.use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached autocomplete results")
                return AutocompleteResult(**cached_result)
        
        # Prepare API parameters
        params = Config.get_autocomplete_params(
            input_text,
            location=location,
            radius=radius,
            language=language
        )
        
        # Make API request
        logger.debug(f"Calling autocomplete API")
        response = make_api_request(Config.PLACES_AUTOCOMPLETE_URL, params=params)
        
        # Parse response
        status = response.get('status', 'UNKNOWN')
        predictions = response.get('predictions', [])
        
        if status == 'OK':
            logger.info(f"Autocomplete successful: {len(predictions)} predictions")
            result = AutocompleteResult(
                predictions=predictions,
                status=status
            )
        elif status == 'ZERO_RESULTS':
            logger.info("Autocomplete returned zero results")
            result = AutocompleteResult(
                predictions=[],
                status=status
            )
        else:
            error_msg = response.get('error_message', f'API returned status: {status}')
            logger.error(f"Autocomplete error: {error_msg}")
            result = AutocompleteResult(
                predictions=[],
                status=status,
                error=error_msg
            )
        
        # Cache successful results
        if self.use_cache and status in ['OK', 'ZERO_RESULTS']:
            self.cache.set(cache_key, {
                'predictions': result.predictions,
                'status': result.status,
                'error': result.error
            })
        
        return result
    
    def get_top_prediction(self, input_text: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get the top prediction for input text.
        
        Args:
            input_text: User input text
            **kwargs: Additional arguments for get_predictions
            
        Returns:
            Top prediction dictionary or None
        """
        result = self.get_predictions(input_text, **kwargs)
        
        if result.predictions:
            return result.predictions[0]
        
        return None
    
    def get_place_ids(self, input_text: str, max_results: int = 5, **kwargs) -> List[str]:
        """
        Get place IDs for input text.
        
        Args:
            input_text: User input text
            max_results: Maximum number of place IDs to return
            **kwargs: Additional arguments for get_predictions
            
        Returns:
            List of place IDs
        """
        result = self.get_predictions(input_text, **kwargs)
        place_ids = result.get_place_ids()
        
        return place_ids[:max_results]
