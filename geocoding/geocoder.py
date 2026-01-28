"""
Google Geocoding API integration with multiple fallback strategies.
"""
from typing import Optional, List, Dict, Any
from .config import Config
from .models import (
    LocationResult, LocationType, AddressComponents,
    NotFoundException, InvalidInputException
)
from .utils import (
    retry_with_backoff, sanitize_input, validate_coordinates,
    parse_address_components, calculate_quality_score, make_api_request
)
from .cache_manager import get_cache_manager
from .logger import Logger

logger = Logger.get_logger(__name__)


class GeocodingService:
    """Service for Google Geocoding API with multiple fallback strategies."""
    
    def __init__(self, use_cache: bool = True):
        """
        Initialize geocoding service.
        
        Args:
            use_cache: Whether to use caching
        """
        self.use_cache = use_cache
        self.cache = get_cache_manager() if use_cache else None
    
    def geocode(self,
                address: Optional[str] = None,
                place_id: Optional[str] = None,
                components: Optional[Dict[str, str]] = None,
                validation_confidence: float = 0.0) -> LocationResult:
        """
        Geocode an address with multiple fallback strategies.
        
        Args:
            address: Address string
            place_id: Google Place ID
            components: Address components dict
            validation_confidence: Confidence from address validation
            
        Returns:
            LocationResult with coordinates and metadata
            
        Raises:
            InvalidInputException: If no valid input provided
            NotFoundException: If location cannot be found
        """
        # Validate input
        if not any([address, place_id, components]):
            raise InvalidInputException("Must provide address, place_id, or components")
        
        logger.info(f"Geocoding request - address: {address}, place_id: {place_id}")
        
        # Strategy 1: Try place_id first (most accurate)
        if place_id:
            try:
                result = self._geocode_by_place_id(place_id, validation_confidence)
                logger.info(f"Geocoded by place_id: {result.latitude}, {result.longitude}")
                return result
            except Exception as e:
                logger.warning(f"Geocoding by place_id failed: {str(e)}")
        
        # Strategy 2: Try full address
        if address:
            try:
                result = self._geocode_by_address(address, validation_confidence)
                logger.info(f"Geocoded by address: {result.latitude}, {result.longitude}")
                return result
            except Exception as e:
                logger.warning(f"Geocoding by address failed: {str(e)}")
        
        # Strategy 3: Try components (fallback for partial addresses)
        if components:
            try:
                result = self._geocode_by_components(components, validation_confidence)
                logger.info(f"Geocoded by components: {result.latitude}, {result.longitude}")
                return result
            except Exception as e:
                logger.warning(f"Geocoding by components failed: {str(e)}")
        
        # All strategies failed
        raise NotFoundException("Unable to geocode location with any strategy")
    
    @retry_with_backoff()
    def _geocode_by_place_id(self, place_id: str, validation_confidence: float = 0.0) -> LocationResult:
        """Geocode using place ID."""
        # Check cache
        cache_key = {
            'service': 'geocoding',
            'place_id': place_id
        }
        
        if self.use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached geocoding result (place_id)")
                return self._parse_cached_result(cached_result)
        
        # Make API request
        params = Config.get_geocoding_params(place_id=place_id)
        response = make_api_request(Config.GEOCODING_URL, params=params)
        
        # Parse and validate result
        result = self._parse_geocoding_response(response, validation_confidence)
        
        # Cache result
        if self.use_cache:
            self.cache.set(cache_key, self._result_to_cache(result))
        
        return result
    
    @retry_with_backoff()
    def _geocode_by_address(self, address: str, validation_confidence: float = 0.0) -> LocationResult:
        """Geocode using address string."""
        address = sanitize_input(address)
        
        # Check cache
        cache_key = {
            'service': 'geocoding',
            'address': address
        }
        
        if self.use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached geocoding result (address)")
                return self._parse_cached_result(cached_result)
        
        # Make API request
        params = Config.get_geocoding_params(address=address)
        response = make_api_request(Config.GEOCODING_URL, params=params)
        
        # Parse and validate result
        result = self._parse_geocoding_response(response, validation_confidence)
        
        # Cache result
        if self.use_cache:
            self.cache.set(cache_key, self._result_to_cache(result))
        
        return result
    
    @retry_with_backoff()
    def _geocode_by_components(self, components: Dict[str, str], 
                               validation_confidence: float = 0.0) -> LocationResult:
        """Geocode using address components."""
        # Build components string
        components_str = '|'.join([f"{k}:{v}" for k, v in components.items() if v])
        
        # Check cache
        cache_key = {
            'service': 'geocoding',
            'components': components_str
        }
        
        if self.use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info("Returning cached geocoding result (components)")
                return self._parse_cached_result(cached_result)
        
        # Make API request
        params = Config.get_geocoding_params(components=components_str)
        response = make_api_request(Config.GEOCODING_URL, params=params)
        
        # Parse and validate result
        result = self._parse_geocoding_response(response, validation_confidence)
        
        # Cache result
        if self.use_cache:
            self.cache.set(cache_key, self._result_to_cache(result))
        
        return result
    
    def _parse_geocoding_response(self, response: dict, 
                                  validation_confidence: float = 0.0) -> LocationResult:
        """Parse geocoding API response."""
        status = response.get('status', 'UNKNOWN')
        
        if status != 'OK':
            error_msg = response.get('error_message', f'Geocoding failed with status: {status}')
            logger.error(f"Geocoding error: {error_msg}")
            raise NotFoundException(error_msg)
        
        results = response.get('results', [])
        if not results:
            raise NotFoundException("No results found")
        
        # Use first result (most relevant)
        result = results[0]
        
        # Extract coordinates
        geometry = result.get('geometry', {})
        location = geometry.get('location', {})
        lat = location.get('lat')
        lon = location.get('lng')
        
        if lat is None or lon is None:
            raise NotFoundException("No coordinates in response")
        
        # Validate coordinates
        is_valid, error_msg = validate_coordinates(lat, lon)
        warnings = []
        if not is_valid:
            warnings.append(error_msg)
            logger.warning(error_msg)
        
        # Extract location type
        location_type_str = geometry.get('location_type', 'UNKNOWN')
        try:
            location_type = LocationType(location_type_str)
        except ValueError:
            location_type = LocationType.UNKNOWN
            warnings.append(f"Unknown location type: {location_type_str}")
        
        # Parse address components
        components_list = result.get('address_components', [])
        parsed_components = parse_address_components(components_list)
        
        address_components = AddressComponents(
            street_address=parsed_components.get('street'),
            locality=parsed_components.get('locality') or parsed_components.get('city'),
            sublocality=None,  # Can be extracted if needed
            administrative_area=parsed_components.get('state'),
            postal_code=parsed_components.get('postal_code'),
            country=parsed_components.get('country', 'India')
        )
        
        # Calculate quality score
        quality_score = calculate_quality_score(
            location_type=location_type_str,
            has_postal_code=bool(address_components.postal_code),
            is_in_india=Config.is_within_india(lat, lon),
            validation_confidence=validation_confidence
        )
        
        # Calculate confidence
        confidence = self._calculate_confidence(location_type, quality_score)
        
        # Extract place_id
        place_id = result.get('place_id')
        
        # Additional metadata
        metadata = {
            'viewport': geometry.get('viewport'),
            'bounds': geometry.get('bounds'),
            'partial_match': result.get('partial_match', False),
            'types': result.get('types', [])
        }
        
        logger.info(
            f"Geocoded successfully - Type: {location_type.value}, "
            f"Quality: {quality_score:.2f}, Confidence: {confidence:.2f}"
        )
        
        return LocationResult(
            latitude=lat,
            longitude=lon,
            location_type=location_type,
            address_components=address_components,
            place_id=place_id,
            confidence=confidence,
            quality_score=quality_score,
            warnings=warnings,
            metadata=metadata
        )
    
    def geocode_by_place_id(self, place_id: str) -> Optional[LocationResult]:
        """
        Public method to geocode using Place ID directly.
        
        This is the most accurate geocoding method when you have a Place ID
        from autocomplete or other sources.
        
        Args:
            place_id: Google Maps Place ID
            
        Returns:
            LocationResult or None if failed
            
        Example:
            location = geocoder.geocode_by_place_id("ChIJLbZ-NFv9DDkRQJY4FbcFcgM")
        """
        try:
            return self._geocode_by_place_id(place_id)
        except Exception as e:
            logger.error(f"Geocoding by Place ID failed: {e}")
            return None
    
    def geocode_by_components(
        self,
        components: Dict[str, str]
    ) -> Optional[LocationResult]:
        """
        Public method to geocode using structured address components.
        
        This method is useful for achieving RANGE_INTERPOLATED precision
        when you have structured address data.
        
        Args:
            components: Dict with keys like 'street_address', 'locality',
                       'administrative_area', 'postal_code', 'country'
                       
        Returns:
            LocationResult or None if failed
            
        Example:
            components = {
                'street_address': '123 MG Road',
                'locality': 'Bangalore',
                'postal_code': '560001',
                'country': 'IN'
            }
            location = geocoder.geocode_by_components(components)
        """
        try:
            # Convert to AddressComponents object
            from models import AddressComponents
            
            addr_components = AddressComponents(
                street_address=components.get('street_address'),
                locality=components.get('locality'),
                sublocality=components.get('sublocality'),
                administrative_area=components.get('administrative_area'),
                postal_code=components.get('postal_code'),
                country=components.get('country', 'India')
            )
            
            return self._geocode_by_components(addr_components)
        except Exception as e:
            logger.error(f"Geocoding by components failed: {e}")
            return None
    
    def _calculate_confidence(self, location_type: LocationType, quality_score: float) -> float:
        """Calculate confidence score."""
        # Base confidence on location type
        type_confidence = {
            LocationType.ROOFTOP: 0.95,
            LocationType.RANGE_INTERPOLATED: 0.85,
            LocationType.GEOMETRIC_CENTER: 0.70,
            LocationType.APPROXIMATE: 0.50,
            LocationType.UNKNOWN: 0.30
        }
        
        base_confidence = type_confidence.get(location_type, 0.30)
        
        # Combine with quality score
        return (base_confidence * 0.7) + (quality_score * 0.3)
    
    def _result_to_cache(self, result: LocationResult) -> dict:
        """Convert LocationResult to cacheable dict."""
        return result.to_dict()
    
    def _parse_cached_result(self, cached: dict) -> LocationResult:
        """Parse cached result back to LocationResult."""
        return LocationResult(
            latitude=cached['latitude'],
            longitude=cached['longitude'],
            location_type=LocationType(cached['location_type']),
            address_components=AddressComponents(**cached['address_components']),
            place_id=cached.get('place_id'),
            confidence=cached['confidence'],
            quality_score=cached['quality_score'],
            warnings=cached.get('warnings', []),
            metadata=cached.get('metadata', {})
        )
