"""
Logging infrastructure for the geocoding pipeline.
"""
import logging
import sys
from pathlib import Path
from typing import Optional
from config import Config


class Logger:
    """Centralized logging system."""
    
    _loggers = {}
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger instance."""
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Avoid adding handlers multiple times
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # File handler
            if Config.LOG_FILE:
                try:
                    # Create log directory if it doesn't exist
                    log_path = Path(Config.LOG_FILE)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    file_handler = logging.FileHandler(Config.LOG_FILE)
                    file_handler.setLevel(logging.DEBUG)
                    file_formatter = logging.Formatter(
                        Config.LOG_FORMAT,
                        datefmt=Config.LOG_DATE_FORMAT
                    )
                    file_handler.setFormatter(file_formatter)
                    logger.addHandler(file_handler)
                except Exception as e:
                    # If file logging fails, just use console
                    pass  # Silent fail for file logging
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def log_api_request(cls, logger: logging.Logger, endpoint: str, params: dict):
        """Log API request details."""
        # Mask API key
        safe_params = params.copy()
        if 'key' in safe_params:
            safe_params['key'] = '***MASKED***'
        
        logger.debug(f"API Request - Endpoint: {endpoint}, Params: {safe_params}")
    
    @classmethod
    def log_api_response(cls, logger: logging.Logger, status_code: int, response_time: float):
        """Log API response details."""
        logger.debug(f"API Response - Status: {status_code}, Time: {response_time:.2f}s")
    
    @classmethod
    def log_cache_event(cls, logger: logging.Logger, event: str, key: str):
        """Log cache events."""
        logger.debug(f"Cache {event} - Key: {key}")
    
    @classmethod
    def log_error(cls, logger: logging.Logger, error: Exception, context: str = ""):
        """Log error with context."""
        if context:
            logger.error(f"{context} - {type(error).__name__}: {str(error)}")
        else:
            logger.error(f"{type(error).__name__}: {str(error)}")
