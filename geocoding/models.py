"""
Data models and schemas for the geocoding pipeline.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class LocationType(Enum):
    """Precision levels for geocoded locations."""
    ROOFTOP = "ROOFTOP"  # Most precise
    RANGE_INTERPOLATED = "RANGE_INTERPOLATED"
    GEOMETRIC_CENTER = "GEOMETRIC_CENTER"
    APPROXIMATE = "APPROXIMATE"
    UNKNOWN = "UNKNOWN"


class ValidationVerdict(Enum):
    """Address validation verdict types."""
    VALID = "VALID"
    INVALID = "INVALID"
    PARTIAL = "PARTIAL"
    UNVALIDATED = "UNVALIDATED"


class ErrorType(Enum):
    """Types of errors that can occur."""
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_PRECISION = "insufficient_precision"  # Precision requirements not met
    UNKNOWN = "unknown"  # Unknown error type
    AUTHENTICATION = "AUTHENTICATION"


@dataclass
class AddressComponents:
    """Structured address components."""
    street_address: Optional[str] = None
    locality: Optional[str] = None
    sublocality: Optional[str] = None
    administrative_area: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'street_address': self.street_address,
            'locality': self.locality,
            'sublocality': self.sublocality,
            'administrative_area': self.administrative_area,
            'postal_code': self.postal_code,
            'country': self.country
        }


@dataclass
class AutocompleteResult:
    """Result from autocomplete API."""
    predictions: List[Dict[str, Any]]
    status: str
    error: Optional[str] = None
    
    def get_place_ids(self) -> List[str]:
        """Extract place IDs from predictions."""
        return [pred.get('place_id') for pred in self.predictions if pred.get('place_id')]
    
    def get_descriptions(self) -> List[str]:
        """Extract descriptions from predictions."""
        return [pred.get('description', '') for pred in self.predictions]


@dataclass
class ValidationResult:
    """Result from address validation API."""
    verdict: ValidationVerdict
    address_components: Optional[AddressComponents] = None
    confidence: float = 0.0
    is_complete: bool = False
    warnings: List[str] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'verdict': self.verdict.value,
            'address_components': self.address_components.to_dict() if self.address_components else None,
            'confidence': self.confidence,
            'is_complete': self.is_complete,
            'warnings': self.warnings
        }


@dataclass
class LocationResult:
    """Final geocoded location result."""
    latitude: float
    longitude: float
    location_type: LocationType
    address_components: AddressComponents
    place_id: Optional[str] = None
    confidence: float = 0.0
    quality_score: float = 0.0
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_in_india(self) -> bool:
        """Check if coordinates are within India bounds."""
        # India approximate bounds: 6°-37°N, 68°-97°E
        return (6.0 <= self.latitude <= 37.0 and 
                68.0 <= self.longitude <= 97.0)
    
    def is_high_precision(self) -> bool:
        """Check if location has high precision."""
        return self.location_type in [LocationType.ROOFTOP, LocationType.RANGE_INTERPOLATED]
    
    def get_uncertainty_radius(self) -> int:
        """
        Get uncertainty radius in meters based on location type and viewport.
        
        This represents the radius within which the actual location likely falls.
        Smaller radius = more precise location.
        
        Returns:
            int: Radius in meters representing location uncertainty
            
        Examples:
            ROOFTOP: 15m (building-level precision)
            RANGE_INTERPOLATED: 75m (street-level)
            GEOMETRIC_CENTER: 1000m (neighborhood center)
            APPROXIMATE: 5000m (city-level)
        """
        # Default conservative radii by location type
        DEFAULT_RADII = {
            LocationType.ROOFTOP: 15,              # ±15m
            LocationType.RANGE_INTERPOLATED: 75,   # ±75m
            LocationType.GEOMETRIC_CENTER: 1000,   # ±1km
            LocationType.APPROXIMATE: 5000,        # ±5km
            LocationType.UNKNOWN: 10000            # ±10km
        }
        
        base_radius = DEFAULT_RADII.get(self.location_type, 10000)
        
        # Calculate actual radius from viewport if available
        viewport = self.metadata.get('viewport')
        if viewport:
            viewport_radius = self._calculate_viewport_radius(viewport)
            # Use the larger of default or calculated (conservative approach)
            return max(base_radius, int(viewport_radius))
        
        return base_radius
    
    def _calculate_viewport_radius(self, viewport: Dict[str, Any]) -> float:
        """
        Calculate radius from viewport bounds using Haversine formula.
        
        Args:
            viewport: Dict with 'northeast' and 'southwest' coordinates
            
        Returns:
            float: Radius in meters from center to corner
        """
        from math import radians, cos, sin, sqrt, atan2
        
        ne = viewport.get('northeast', {})
        sw = viewport.get('southwest', {})
        
        # Calculate center point
        center_lat = (ne.get('lat', 0) + sw.get('lat', 0)) / 2
        center_lng = (ne.get('lng', 0) + sw.get('lng', 0)) / 2
        
        # Haversine distance from center to NE corner
        R = 6371000  # Earth radius in meters
        
        phi1 = radians(center_lat)
        phi2 = radians(ne.get('lat', center_lat))
        dphi = radians(ne.get('lat', center_lat) - center_lat)
        dlambda = radians(ne.get('lng', center_lng) - center_lng)
        
        a = sin(dphi/2)**2 + cos(phi1) * cos(phi2) * sin(dlambda/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    def should_use_radius(self) -> bool:
        """
        Determine if radius-based approach should be used instead of exact coordinates.
        
        Returns True for locations that are too imprecise for exact point-based operations.
        
        Returns:
            bool: True if location requires radius-based approach
            
        Usage:
            if location.should_use_radius():
                # Use center + radius for fuzzy matching
                search_nearby(lat, lng, radius)
            else:
                # Use exact coordinates
                navigate_to(lat, lng)
        """
        return self.location_type in [
            LocationType.GEOMETRIC_CENTER,
            LocationType.APPROXIMATE,
            LocationType.UNKNOWN
        ]
    
    def get_precision_level(self) -> str:
        """
        Get human-readable precision level.
        
        Returns:
            str: 'high', 'medium', 'low', or 'very_low'
            
        Levels:
            - high: ROOFTOP (±15m)
            - medium: RANGE_INTERPOLATED (±75m)
            - low: GEOMETRIC_CENTER (±1km)
            - very_low: APPROXIMATE/UNKNOWN (±5-10km)
        """
        if self.location_type == LocationType.ROOFTOP:
            return 'high'
        elif self.location_type == LocationType.RANGE_INTERPOLATED:
            return 'medium'
        elif self.location_type == LocationType.GEOMETRIC_CENTER:
            return 'low'
        else:
            return 'very_low'
    
    def to_precision_dict(self) -> Dict[str, Any]:
        """
        Export location with complete precision metadata.
        
        Useful for API responses where precision information is critical.
        
        Returns:
            dict: Complete location data with precision metadata
            
        Example output:
            {
                'latitude': 28.6129,
                'longitude': 77.2295,
                'precision_level': 'high',
                'location_type': 'ROOFTOP',
                'use_radius': False,
                'uncertainty_radius': 15,
                'quality_score': 0.95,
                'confidence': 0.90,
                'formatted_address': 'India Gate, New Delhi, Delhi, 110001',
                'is_high_precision': True,
                'is_in_india': True
            }
        """
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'precision_level': self.get_precision_level(),
            'location_type': self.location_type.value,
            'use_radius': self.should_use_radius(),
            'uncertainty_radius': self.get_uncertainty_radius(),
            'quality_score': self.quality_score,
            'confidence': self.confidence,
            'formatted_address': self._get_formatted_address(),
            'is_high_precision': self.is_high_precision(),
            'is_in_india': self.is_in_india(),
            'place_id': self.place_id,
            'warnings': self.warnings
        }
    
    def _get_formatted_address(self) -> str:
        """Get formatted address string from components."""
        parts = []
        if self.address_components.locality:
            parts.append(self.address_components.locality)
        if self.address_components.sublocality:
            parts.append(self.address_components.sublocality)
        if self.address_components.administrative_area:
            parts.append(self.address_components.administrative_area)
        if self.address_components.postal_code:
            parts.append(self.address_components.postal_code)
        return ', '.join(filter(None, parts))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'location_type': self.location_type.value,
            'address_components': self.address_components.to_dict(),
            'place_id': self.place_id,
            'confidence': self.confidence,
            'quality_score': self.quality_score,
            'warnings': self.warnings,
            'is_in_india': self.is_in_india(),
            'is_high_precision': self.is_high_precision(),
            'metadata': self.metadata
        }


@dataclass
class PipelineResult:
    """Complete pipeline execution result."""
    success: bool
    location: Optional[LocationResult] = None
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None
    autocomplete_results: Optional[AutocompleteResult] = None
    validation_result: Optional[ValidationResult] = None
    processing_time: float = 0.0
    cache_hit: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'success': self.success,
            'processing_time': self.processing_time,
            'cache_hit': self.cache_hit
        }
        
        if self.location:
            result['location'] = self.location.to_dict()
        
        if self.validation_result:
            result['validation'] = self.validation_result.to_dict()
        
        if self.error_type:
            result['error'] = {
                'type': self.error_type.value,
                'message': self.error_message
            }
        
        return result


class GeocodingException(Exception):
    """Base exception for geocoding errors."""
    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


class APIException(GeocodingException):
    """Exception for API-related errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message, ErrorType.API_ERROR)


class NetworkException(GeocodingException):
    """Exception for network-related errors."""
    def __init__(self, message: str):
        super().__init__(message, ErrorType.NETWORK_ERROR)


class InvalidInputException(GeocodingException):
    """Exception for invalid input errors."""
    def __init__(self, message: str):
        super().__init__(message, ErrorType.INVALID_INPUT)


class NotFoundException(GeocodingException):
    """Exception when location is not found."""
    def __init__(self, message: str):
        super().__init__(message, ErrorType.NOT_FOUND)
