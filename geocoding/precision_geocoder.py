"""Advanced Precision Geocoding System with Intelligent Fallbacks."""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from .config import Config
from .models import (
    LocationResult, LocationType, AddressComponents,
    PipelineResult, ErrorType, GeocodingException,
    InvalidInputException, NotFoundException
)
from .autocomplete import AutocompleteService
from .address_validator import AddressValidationService
from .geocoder import GeocodingService
from .utils import sanitize_input, is_valid_input
from .cache_manager import get_cache_manager
from .logger import Logger

logger = Logger.get_logger(__name__)


class PrecisionLevel(Enum):
    """Precision level requirements."""
    EXACT = "exact"              # ROOFTOP only (±15m)
    HIGH = "high"                # ROOFTOP or RANGE_INTERPOLATED (±75m)
    MEDIUM = "medium"            # Accept GEOMETRIC_CENTER (±1km)
    ANY = "any"                  # Accept all types


@dataclass
class PrecisionConfig:
    """Configuration for precision requirements."""
    min_precision: PrecisionLevel = PrecisionLevel.HIGH
    max_radius: Optional[int] = None  # Max acceptable uncertainty radius in meters
    min_quality_score: float = 0.5
    enable_enhancement: bool = True   # Try to enhance low-precision results
    enable_interpolation: bool = True # Use RANGE_INTERPOLATED strategy
    max_enhancement_attempts: int = 3


class PrecisionGeocoder:
    """Advanced geocoding system with precision optimization using 5-stage fallback strategy."""
    
    def __init__(
        self,
        precision_config: Optional[PrecisionConfig] = None,
        use_cache: bool = True
    ):
        """
        Initialize precision geocoder.
        
        Args:
            precision_config: Precision requirements configuration
            use_cache: Whether to use caching
        """
        self.config = precision_config or PrecisionConfig()
        self.autocomplete = AutocompleteService(use_cache=use_cache)
        self.validator = AddressValidationService(use_cache=use_cache)
        self.geocoder = GeocodingService(use_cache=use_cache)
        self.cache = get_cache_manager() if use_cache else None
        
        logger.info(
            f"PrecisionGeocoder initialized - "
            f"Min precision: {self.config.min_precision.value}, "
            f"Enhancement: {self.config.enable_enhancement}"
        )
    
    def geocode(
        self,
        address: str,
        precision_level: Optional[PrecisionLevel] = None
    ) -> PipelineResult:
        """Geocode address with maximum precision using multiple strategies."""
        # Use provided precision level or default
        required_precision = precision_level or self.config.min_precision
        
        logger.info(f"Starting precision geocoding for: '{address}'")
        logger.info(f"Required precision: {required_precision.value}")
        
        # Validate input
        if not address or not is_valid_input(address):
            return PipelineResult(
                success=False,
                error_type=ErrorType.INVALID_INPUT,
                error_message="Invalid or empty address provided"
            )
        
        # Sanitize input
        clean_address = sanitize_input(address)
        
        # Try strategies in order of precision
        strategies = [
            ("Direct Geocoding", self._strategy_direct),
            ("Autocomplete + Place ID", self._strategy_autocomplete_placeid),
            ("Validation + Enhanced", self._strategy_validation_enhanced),
            ("Component-Based", self._strategy_component_based),
            ("Fallback with Radius", self._strategy_fallback_radius)
        ]
        
        last_result = None
        
        for strategy_name, strategy_func in strategies:
            logger.info(f"Trying strategy: {strategy_name}")
            
            try:
                result = strategy_func(clean_address)
                
                if result and result.success:
                    # Check if precision meets requirements
                    if self._meets_precision_requirements(
                        result.location,
                        required_precision
                    ):
                        logger.info(
                            f"✅ Success with {strategy_name} - "
                            f"Type: {result.location.location_type.value}, "
                            f"Quality: {result.location.quality_score:.2f}"
                        )
                        return result
                    else:
                        logger.info(
                            f"⚠️ {strategy_name} succeeded but precision insufficient - "
                            f"Got: {result.location.location_type.value}, "
                            f"Need: {required_precision.value}"
                        )
                        last_result = result
                        
            except Exception as e:
                logger.warning(f"Strategy '{strategy_name}' failed: {str(e)}")
                continue
        
        # All strategies failed or didn't meet precision
        if last_result and last_result.success:
            # We got a result but it doesn't meet precision requirements
            return PipelineResult(
                success=False,
                location=last_result.location,
                error_type=ErrorType.INSUFFICIENT_PRECISION,
                error_message=(
                    f"Address geocoded but precision insufficient. "
                    f"Got: {last_result.location.location_type.value} "
                    f"(±{last_result.location.get_uncertainty_radius()}m), "
                    f"Required: {required_precision.value}. "
                    f"Please provide more specific address details."
                )
            )
        
        # Complete failure
        return PipelineResult(
            success=False,
            error_type=ErrorType.NOT_FOUND,
            error_message="Unable to geocode address with any strategy"
        )
    
    def _strategy_direct(self, address: str) -> Optional[PipelineResult]:
        """
        Strategy 1: Direct geocoding.
        
        Best for: Complete, well-formatted addresses
        Expected precision: ROOFTOP or RANGE_INTERPOLATED
        """
        try:
            location = self.geocoder.geocode(address)
            if location:
                return PipelineResult(
                    success=True,
                    location=location,
                    metadata={'strategy': 'direct'}
                )
        except Exception as e:
            logger.debug(f"Direct geocoding failed: {e}")
        
        return None
    
    def _strategy_autocomplete_placeid(
        self,
        address: str
    ) -> Optional[PipelineResult]:
        """
        Strategy 2: Autocomplete to get Place ID, then geocode.
        
        Best for: Partial addresses, landmarks
        Expected precision: ROOFTOP (landmarks) or GEOMETRIC_CENTER (areas)
        
        This is the MOST IMPORTANT strategy for improving precision!
        """
        try:
            # Get autocomplete suggestions
            suggestions = self.autocomplete.get_suggestions(
                address,
                components={'country': 'in'}
            )
            
            if not suggestions or not suggestions.predictions:
                return None
            
            # Try top 3 suggestions
            for i, prediction in enumerate(suggestions.predictions[:3]):
                place_id = prediction.get('place_id')
                if not place_id:
                    continue
                
                logger.debug(
                    f"Trying autocomplete suggestion {i+1}: "
                    f"{prediction.get('description')}"
                )
                
                # Geocode using Place ID (most accurate!)
                location = self.geocoder.geocode_by_place_id(place_id)
                
                if location and location.is_high_precision():
                    logger.info(
                        f"✅ Autocomplete enhanced precision to "
                        f"{location.location_type.value}"
                    )
                    return PipelineResult(
                        success=True,
                        location=location,
                        metadata={
                            'strategy': 'autocomplete_placeid',
                            'original_address': address,
                            'enhanced_address': prediction.get('description')
                        }
                    )
                
                # Keep best result even if not high precision
                if location:
                    return PipelineResult(
                        success=True,
                        location=location,
                        metadata={
                            'strategy': 'autocomplete_placeid',
                            'enhanced_address': prediction.get('description')
                        }
                    )
        
        except Exception as e:
            logger.debug(f"Autocomplete + Place ID strategy failed: {e}")
        
        return None
    
    def _strategy_validation_enhanced(
        self,
        address: str
    ) -> Optional[PipelineResult]:
        """
        Strategy 3: Validate address, then geocode enhanced version.
        
        Best for: Messy or incomplete addresses
        Expected precision: RANGE_INTERPOLATED or GEOMETRIC_CENTER
        """
        try:
            # Validate and get standardized address
            validation = self.validator.validate(address)
            
            if not validation or not validation.address_components:
                return None
            
            # Build enhanced address from validated components
            enhanced_address = self._build_enhanced_address(
                validation.address_components
            )
            
            if enhanced_address:
                logger.debug(f"Enhanced address: {enhanced_address}")
                
                # Geocode enhanced address
                location = self.geocoder.geocode(enhanced_address)
                
                if location:
                    return PipelineResult(
                        success=True,
                        location=location,
                        metadata={
                            'strategy': 'validation_enhanced',
                            'original_address': address,
                            'enhanced_address': enhanced_address
                        }
                    )
        
        except Exception as e:
            logger.debug(f"Validation + Enhanced strategy failed: {e}")
        
        return None
    
    def _strategy_component_based(
        self, 
        address: str
    ) -> Optional[PipelineResult]:
        """
        Strategy 4: Component-based geocoding for RANGE_INTERPOLATED.
        
        Best for: Addresses with street numbers but poor formatting
        Expected precision: RANGE_INTERPOLATED
        
        This strategy tries to extract components and geocode using
        structured component query for better street-level precision.
        """
        if not self.config.enable_interpolation:
            return None
        
        try:
            # Extract components from address
            components = self._extract_address_components(address)
            
            if components:
                # Try geocoding with components
                location = self.geocoder.geocode_by_components(components)
                
                if location and location.location_type == LocationType.RANGE_INTERPOLATED:
                    logger.info("✅ Component-based geocoding achieved RANGE_INTERPOLATED")
                    return PipelineResult(
                        success=True,
                        location=location,
                        metadata={
                            'strategy': 'component_based',
                            'components': components
                        }
                    )
        
        except Exception as e:
            logger.debug(f"Component-based strategy failed: {e}")
        
        return None
    
    def _strategy_fallback_radius(
        self,
        address: str
    ) -> Optional[PipelineResult]:
        """
        Strategy 5: Fallback with radius-based result.
        
        Best for: Very incomplete addresses (city, postal code only)
        Expected precision: GEOMETRIC_CENTER or APPROXIMATE
        
        This is the last resort - accept lower precision with radius.
        """
        try:
            # Try basic geocoding
            location = self.geocoder.geocode(address)
            
            if location:
                # Mark as radius-based
                location.warnings.append(
                    f"Low precision result. Using center point with "
                    f"±{location.get_uncertainty_radius()}m radius."
                )
                
                return PipelineResult(
                    success=True,
                    location=location,
                    metadata={
                        'strategy': 'fallback_radius',
                        'use_radius': True,
                        'radius': location.get_uncertainty_radius()
                    }
                )
        
        except Exception as e:
            logger.debug(f"Fallback radius strategy failed: {e}")
        
        return None
    
    def _meets_precision_requirements(
        self,
        location: LocationResult,
        required_precision: PrecisionLevel
    ) -> bool:
        """
        Check if location meets precision requirements.
        
        Args:
            location: Geocoded location result
            required_precision: Required precision level
            
        Returns:
            bool: True if requirements are met
        """
        # Check precision level
        if required_precision == PrecisionLevel.EXACT:
            if location.location_type != LocationType.ROOFTOP:
                return False
        
        elif required_precision == PrecisionLevel.HIGH:
            if not location.is_high_precision():
                return False
        
        elif required_precision == PrecisionLevel.MEDIUM:
            if location.location_type in [LocationType.APPROXIMATE, LocationType.UNKNOWN]:
                return False
        
        # PrecisionLevel.ANY accepts all
        
        # Check max radius if specified
        if self.config.max_radius:
            if location.get_uncertainty_radius() > self.config.max_radius:
                return False
        
        # Check quality score
        if location.quality_score < self.config.min_quality_score:
            return False
        
        return True
    
    def _build_enhanced_address(
        self,
        components: AddressComponents
    ) -> Optional[str]:
        """
        Build enhanced address from validated components.
        
        Args:
            components: Validated address components
            
        Returns:
            Enhanced address string or None
        """
        parts = []
        
        # Add components in order of specificity
        if components.street_address:
            parts.append(components.street_address)
        if components.sublocality:
            parts.append(components.sublocality)
        if components.locality:
            parts.append(components.locality)
        if components.administrative_area:
            parts.append(components.administrative_area)
        if components.postal_code:
            parts.append(components.postal_code)
        if components.country:
            parts.append(components.country)
        
        if parts:
            return ', '.join(parts)
        
        return None
    
    def _extract_address_components(
        self,
        address: str
    ) -> Optional[Dict[str, str]]:
        """
        Extract structured components from free-form address.
        
        Args:
            address: Free-form address string
            
        Returns:
            Dict of components for geocoding API
        """
        import re
        
        components = {}
        
        # Extract postal code (6 digits in India)
        postal_match = re.search(r'\b\d{6}\b', address)
        if postal_match:
            components['postal_code'] = postal_match.group()
        
        # Extract state names (common Indian states)
        states = [
            'Delhi', 'Mumbai', 'Maharashtra', 'Karnataka', 'Tamil Nadu',
            'Kerala', 'Gujarat', 'Rajasthan', 'West Bengal', 'Uttar Pradesh',
            'Telangana', 'Andhra Pradesh', 'Punjab', 'Haryana'
        ]
        for state in states:
            if state.lower() in address.lower():
                components['administrative_area'] = state
                break
        
        # Always add country
        components['country'] = 'IN'
        
        return components if len(components) > 1 else None
    
    def batch_geocode(
        self,
        addresses: List[str],
        precision_level: Optional[PrecisionLevel] = None
    ) -> List[PipelineResult]:
        """
        Geocode multiple addresses with precision optimization.
        
        Args:
            addresses: List of addresses to geocode
            precision_level: Required precision level
            
        Returns:
            List of PipelineResult objects
        """
        results = []
        
        logger.info(f"Starting batch geocoding for {len(addresses)} addresses")
        
        for i, address in enumerate(addresses, 1):
            logger.info(f"Processing {i}/{len(addresses)}: {address}")
            
            result = self.geocode(address, precision_level)
            results.append(result)
            
            if result.success:
                logger.info(
                    f"  ✅ Success - {result.location.location_type.value} "
                    f"(±{result.location.get_uncertainty_radius()}m)"
                )
            else:
                logger.warning(f"  ❌ Failed - {result.error_message}")
        
        # Summary
        successful = sum(1 for r in results if r.success)
        logger.info(
            f"Batch complete: {successful}/{len(addresses)} successful "
            f"({successful/len(addresses)*100:.1f}%)"
        )
        
        return results


def quick_precision_geocode(
    address: str,
    precision: str = "high"
) -> Optional[Dict[str, Any]]:
    """
    Quick helper function for precision geocoding.
    
    Args:
        address: Address to geocode
        precision: 'exact', 'high', 'medium', or 'any'
        
    Returns:
        Dict with location and precision data, or None if failed
        
    Example:
        >>> result = quick_precision_geocode("India Gate, Delhi", "high")
        >>> print(result['latitude'], result['longitude'])
        >>> print(f"Precision: {result['precision_level']} (±{result['radius']}m)")
    """
    precision_map = {
        'exact': PrecisionLevel.EXACT,
        'high': PrecisionLevel.HIGH,
        'medium': PrecisionLevel.MEDIUM,
        'any': PrecisionLevel.ANY
    }
    
    precision_level = precision_map.get(precision.lower(), PrecisionLevel.HIGH)
    
    geocoder = PrecisionGeocoder(
        precision_config=PrecisionConfig(min_precision=precision_level)
    )
    
    result = geocoder.geocode(address)
    
    if result.success:
        return result.location.to_precision_dict()
    
    return None


if __name__ == "__main__":
    # Example usage
    print("=" * 70)
    print("PRECISION GEOCODING SYSTEM - DEMO")
    print("=" * 70)
    
    # Test addresses with varying quality
    test_cases = [
        ("India Gate, New Delhi", PrecisionLevel.EXACT),
        ("Forum Mall, Koramangala", PrecisionLevel.HIGH),
        ("Koramangala, Bangalore", PrecisionLevel.MEDIUM),
        ("560001", PrecisionLevel.ANY),
        ("near bus stop jp nagar", PrecisionLevel.HIGH),  # Messy
        ("123 MG Road Bangalore", PrecisionLevel.HIGH),   # Incomplete
    ]
    
    geocoder = PrecisionGeocoder()
    
    for address, precision in test_cases:
        print(f"\n{'='*70}")
        print(f"Address: {address}")
        print(f"Required Precision: {precision.value}")
        print('-' * 70)
        
        result = geocoder.geocode(address, precision)
        
        if result.success:
            loc = result.location
            print(f"✅ SUCCESS")
            print(f"   Strategy: {result.metadata.get('strategy', 'unknown')}")
            print(f"   Lat/Lng: {loc.latitude:.6f}, {loc.longitude:.6f}")
            print(f"   Type: {loc.location_type.value}")
            print(f"   Precision: {loc.get_precision_level()}")
            print(f"   Radius: ±{loc.get_uncertainty_radius()}m")
            print(f"   Quality: {loc.quality_score:.2f}")
            print(f"   Use Radius: {loc.should_use_radius()}")
            
            if loc.warnings:
                print(f"   Warnings: {', '.join(loc.warnings)}")
        else:
            print(f"❌ FAILED")
            print(f"   Error: {result.error_message}")
