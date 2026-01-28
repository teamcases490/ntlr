"""
Main pipeline orchestrator for the geocoding system.
Handles the complete flow: Input → Autocomplete → Validation → Geocoding
"""
import time
from typing import Optional, Dict, Any, List
from .config import Config
from .models import (
    PipelineResult, LocationResult, ErrorType,
    GeocodingException, InvalidInputException, NotFoundException
)
from .autocomplete import AutocompleteService
from .address_validator import AddressValidationService
from .geocoder import GeocodingService
from .utils import sanitize_input
from .logger import Logger

logger = Logger.get_logger(__name__)


class GeocodingPipeline:
    """Production-ready geocoding pipeline with comprehensive error handling."""
    
    def __init__(self, use_cache: bool = True):
        """
        Initialize pipeline with all services.
        
        Args:
            use_cache: Whether to use caching
        """
        self.autocomplete = AutocompleteService(use_cache=use_cache)
        self.validator = AddressValidationService(use_cache=use_cache)
        self.geocoder = GeocodingService(use_cache=use_cache)
        self.use_cache = use_cache
        
        logger.info("Geocoding pipeline initialized")
    
    def process(self, user_input: str) -> PipelineResult:
        """
        Process user input through the complete pipeline.
        
        This method ALWAYS uses:
        - Autocomplete: To get accurate place predictions
        - Validation: To verify and standardize addresses
        - Geocoding: To extract precise coordinates
        
        Args:
            user_input: User's location input (any Indian address)
            
        Returns:
            PipelineResult with location or error details
        """
        start_time = time.time()
        cache_hit = False
        
        try:
            logger.info(f"=== Pipeline started for: '{user_input[:50]}...' ===")
            
            # Sanitize input
            user_input = sanitize_input(user_input)
            if not user_input:
                raise InvalidInputException("Empty input after sanitization")
            
            # Step 1: Autocomplete (ALWAYS ENABLED for accuracy)
            logger.info("Step 1: Getting autocomplete predictions")
            autocomplete_result = self.autocomplete.get_predictions(user_input)
            
            selected_prediction = None
            place_id = None
            
            if autocomplete_result.error:
                logger.warning(f"Autocomplete error: {autocomplete_result.error}")
            elif autocomplete_result.predictions:
                # Always select top prediction for best accuracy
                selected_prediction = autocomplete_result.predictions[0]
                place_id = selected_prediction.get('place_id')
                user_input = selected_prediction.get('description', user_input)
                logger.info(f"Selected top prediction: {user_input}")
            
            # Step 2: Address Validation (ALWAYS ENABLED for quality)
            logger.info("Step 2: Validating address")
            validation_result = None
            validation_confidence = 0.0
            
            try:
                validation_result = self.validator.validate_address(user_input)
                validation_confidence = validation_result.confidence
                
                # Validation result available but we don't use standardized address
                # since AddressComponents doesn't have formatted_address anymore
                
            except Exception as e:
                logger.warning(f"Validation failed, continuing without it: {str(e)}")
            
            # Step 3: Geocoding with fallbacks
            logger.info("Step 3: Geocoding location")
            location = self._geocode_with_fallbacks(
                address=user_input,
                place_id=place_id,
                validation_result=validation_result,
                validation_confidence=validation_confidence
            )
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            logger.info(
                f"=== Pipeline completed successfully in {processing_time:.2f}s ==="
            )
            
            return PipelineResult(
                success=True,
                location=location,
                autocomplete_results=autocomplete_result,
                validation_result=validation_result,
                processing_time=processing_time,
                cache_hit=cache_hit
            )
            
        except InvalidInputException as e:
            processing_time = time.time() - start_time
            logger.error(f"Invalid input: {str(e)}")
            return PipelineResult(
                success=False,
                error_type=ErrorType.INVALID_INPUT,
                error_message=str(e),
                processing_time=processing_time
            )
        
        except NotFoundException as e:
            processing_time = time.time() - start_time
            logger.error(f"Location not found: {str(e)}")
            return PipelineResult(
                success=False,
                error_type=ErrorType.NOT_FOUND,
                error_message=str(e),
                processing_time=processing_time
            )
        
        except GeocodingException as e:
            processing_time = time.time() - start_time
            logger.error(f"Geocoding error: {str(e)}")
            return PipelineResult(
                success=False,
                error_type=e.error_type,
                error_message=str(e),
                processing_time=processing_time
            )
        
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return PipelineResult(
                success=False,
                error_type=ErrorType.UNKNOWN,
                error_message=f"Unexpected error: {str(e)}",
                processing_time=processing_time
            )
    
    def _geocode_with_fallbacks(self,
                                address: str,
                                place_id: Optional[str],
                                validation_result: Optional[Any],
                                validation_confidence: float) -> LocationResult:
        """
        Geocode with multiple fallback strategies.
        
        Priority:
        1. Place ID (most accurate)
        2. Full address
        3. Address components from validation
        """
        # Try place_id first
        if place_id:
            try:
                return self.geocoder.geocode(
                    place_id=place_id,
                    validation_confidence=validation_confidence
                )
            except Exception as e:
                logger.warning(f"Geocoding by place_id failed: {str(e)}")
        
        # Try full address
        try:
            return self.geocoder.geocode(
                address=address,
                validation_confidence=validation_confidence
            )
        except Exception as e:
            logger.warning(f"Geocoding by address failed: {str(e)}")
        
        # Try components from validation
        if validation_result and validation_result.address_components:
            components = {}
            addr_comp = validation_result.address_components
            
            if addr_comp.locality:
                components['locality'] = addr_comp.locality
            if addr_comp.administrative_area:
                components['administrative_area'] = addr_comp.administrative_area
            if addr_comp.postal_code:
                components['postal_code'] = addr_comp.postal_code
            components['country'] = 'IN'
            
            if components:
                try:
                    return self.geocoder.geocode(
                        components=components,
                        validation_confidence=validation_confidence
                    )
                except Exception as e:
                    logger.warning(f"Geocoding by components failed: {str(e)}")
        
        # All strategies failed
        raise NotFoundException("Unable to geocode location with any strategy")
    
    def process_batch(self, inputs: List[str], **kwargs) -> List[PipelineResult]:
        """
        Process multiple inputs in batch.
        
        Args:
            inputs: List of user inputs
            **kwargs: Arguments to pass to process()
            
        Returns:
            List of PipelineResults
        """
        logger.info(f"Processing batch of {len(inputs)} inputs")
        results = []
        
        for i, user_input in enumerate(inputs, 1):
            logger.info(f"Processing {i}/{len(inputs)}")
            result = self.process(user_input, **kwargs)
            results.append(result)
        
        return results
    
    def get_location(self, user_input: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Simplified method to get just the location data.
        
        Args:
            user_input: User's location input
            **kwargs: Arguments to pass to process()
            
        Returns:
            Location dictionary or None if failed
        """
        result = self.process(user_input, **kwargs)
        
        if result.success and result.location:
            return result.location.to_dict()
        
        return None
    
    def get_coordinates(self, user_input: str, **kwargs) -> Optional[tuple]:
        """
        Get just the coordinates (lat, lon).
        
        Args:
            user_input: User's location input
            **kwargs: Arguments to pass to process()
            
        Returns:
            Tuple of (latitude, longitude) or None if failed
        """
        result = self.process(user_input, **kwargs)
        
        if result.success and result.location:
            return (result.location.latitude, result.location.longitude)
        
        return None


def quick_geocode(address: str) -> Optional[tuple]:
    """
    Quick helper function to geocode an address.
    
    Args:
        address: Address to geocode
        
    Returns:
        Tuple of (latitude, longitude) or None
    """
    pipeline = GeocodingPipeline()
    return pipeline.get_coordinates(address)
