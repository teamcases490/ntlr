"""
Google Address Validation API integration.
"""
from typing import Optional
from .config import Config
from .models import (
    ValidationResult, ValidationVerdict, AddressComponents,
    InvalidInputException
)
from .utils import (
    retry_with_backoff, sanitize_input, is_valid_input,
    parse_address_components, make_api_request
)
from .cache_manager import get_cache_manager
from .logger import Logger

logger = Logger.get_logger(__name__)


class AddressValidationService:
    """Service for Google Address Validation API."""
    
    def __init__(self, use_cache: bool = True):
        """
        Initialize address validation service.
        
        Args:
            use_cache: Whether to use caching
        """
        self.use_cache = use_cache
        self.cache = get_cache_manager() if use_cache else None
    
    @retry_with_backoff()
    def validate_address(self, address: str) -> ValidationResult:
        """
        Validate an address using Google Address Validation API.
        
        Args:
            address: Address string to validate
            
        Returns:
            ValidationResult with verdict and standardized address
            
        Raises:
            InvalidInputException: If address is invalid
        """
        # Sanitize and validate input
        address = sanitize_input(address)
        is_valid, error_msg = is_valid_input(address)
        if not is_valid:
            logger.warning(f"Invalid address input: {error_msg}")
            raise InvalidInputException(error_msg)
        
        logger.info(f"Validating address: '{address[:50]}...'")
        
        # Check cache
        cache_key = {
            'service': 'validation',
            'address': address
        }
        
        if self.use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached validation result")
                return self._parse_cached_result(cached_result)
        
        # Prepare API payload
        payload = Config.get_validation_payload(address)
        
        # Make API request
        logger.debug("Calling address validation API")
        try:
            response = make_api_request(
                Config.ADDRESS_VALIDATION_URL,
                json_data=payload,
                method='POST'
            )
            
            # Parse response
            result = self._parse_validation_response(response, address)
            
            # Cache result
            if self.use_cache:
                self.cache.set(cache_key, self._result_to_cache(result))
            
            return result
            
        except Exception as e:
            # If validation API fails, return unvalidated result
            logger.warning(f"Address validation failed: {str(e)}. Returning unvalidated.")
            return ValidationResult(
                verdict=ValidationVerdict.UNVALIDATED,
                address_components=AddressComponents(locality=address),
                confidence=0.0,
                is_complete=False,
                warnings=[f"Validation unavailable: {str(e)}"]
            )
    
    def _parse_validation_response(self, response: dict, original_address: str) -> ValidationResult:
        """Parse validation API response."""
        result = response.get('result', {})
        verdict_data = result.get('verdict', {})
        address_data = result.get('address', {})
        
        # Determine verdict
        validation_granularity = verdict_data.get('validationGranularity', 'UNKNOWN')
        has_unconfirmed = verdict_data.get('hasUnconfirmedComponents', True)
        has_inferred = verdict_data.get('hasInferredComponents', False)
        
        if validation_granularity in ['PREMISE', 'SUB_PREMISE']:
            if not has_unconfirmed:
                verdict = ValidationVerdict.VALID
                confidence = 0.95
            else:
                verdict = ValidationVerdict.PARTIAL
                confidence = 0.7
        elif validation_granularity in ['ROUTE', 'LOCALITY']:
            verdict = ValidationVerdict.PARTIAL
            confidence = 0.6
        else:
            verdict = ValidationVerdict.INVALID
            confidence = 0.3
        
        # Extract address components
        formatted_address = address_data.get('formattedAddress', original_address)
        postal_address = address_data.get('postalAddress', {})
        address_components_list = address_data.get('addressComponents', [])
        
        # Parse components
        parsed_components = self._parse_components(address_components_list, postal_address)
        
        address_components = AddressComponents(
            street_address=parsed_components.get('street'),
            locality=parsed_components.get('locality') or parsed_components.get('city'),
            sublocality=None,  # Not provided by validation API
            administrative_area=parsed_components.get('state'),
            postal_code=parsed_components.get('postal_code'),
            country=postal_address.get('regionCode', 'IN')
        )
        
        # Check completeness
        is_complete = all([
            address_components.locality,
            address_components.administrative_area,
            address_components.postal_code
        ])
        
        # Collect warnings
        warnings = []
        if has_unconfirmed:
            warnings.append("Address has unconfirmed components")
        if has_inferred:
            warnings.append("Some components were inferred")
        if not is_complete:
            warnings.append("Address is incomplete")
        
        logger.info(f"Validation result: {verdict.value}, confidence: {confidence:.2f}")
        
        return ValidationResult(
            verdict=verdict,
            address_components=address_components,
            confidence=confidence,
            is_complete=is_complete,
            warnings=warnings,
            raw_response=result
        )
    
    def _parse_components(self, components_list: list, postal_address: dict) -> dict:
        """Parse address components from validation response."""
        result = {
            'street': None,
            'locality': None,
            'city': None,
            'state': None,
            'postal_code': None
        }
        
        # Try to get from postal address first
        result['postal_code'] = postal_address.get('postalCode')
        result['state'] = postal_address.get('administrativeArea')
        result['city'] = postal_address.get('locality')
        
        # Parse from components list
        for component in components_list:
            component_type = component.get('componentType', '')
            component_name = component.get('componentName', {}).get('text', '')
            
            if component_type == 'route' and not result['street']:
                result['street'] = component_name
            elif component_type == 'sublocality' and not result['locality']:
                result['locality'] = component_name
            elif component_type == 'locality' and not result['city']:
                result['city'] = component_name
            elif component_type == 'administrative_area_level_1' and not result['state']:
                result['state'] = component_name
            elif component_type == 'postal_code' and not result['postal_code']:
                result['postal_code'] = component_name
        
        return result
    
    def _result_to_cache(self, result: ValidationResult) -> dict:
        """Convert ValidationResult to cacheable dict."""
        return {
            'verdict': result.verdict.value,
            'address_components': result.address_components.to_dict() if result.address_components else None,
            'confidence': result.confidence,
            'is_complete': result.is_complete,
            'warnings': result.warnings
        }
    
    def _parse_cached_result(self, cached: dict) -> ValidationResult:
        """Parse cached result back to ValidationResult."""
        address_components = None
        if cached.get('address_components'):
            address_components = AddressComponents(**cached['address_components'])
        
        return ValidationResult(
            verdict=ValidationVerdict(cached['verdict']),
            address_components=address_components,
            confidence=cached['confidence'],
            is_complete=cached['is_complete'],
            warnings=cached['warnings']
        )
