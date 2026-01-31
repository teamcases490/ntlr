import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
    GEE_PROJECT_ID = os.getenv('GEE_PROJECT_ID', 'incomeestimationcase-468413')
    SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE', 'credentials.json')
    
    DEFAULT_REGION = 'IN'
    DEFAULT_LANGUAGE = 'en'
    INDIA_BOUNDS = {
        'lat_min': 6.0, 'lat_max': 37.0,
        'lon_min': 68.0, 'lon_max': 97.0
    }
    
    PLACES_AUTOCOMPLETE_URL = 'https://maps.googleapis.com/maps/api/place/autocomplete/json'
    ADDRESS_VALIDATION_URL = 'https://addressvalidation.googleapis.com/v1:validateAddress'
    GEOCODING_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    RETRY_BACKOFF = 2.0
    REQUEST_TIMEOUT = 10
    
    CACHE_ENABLED = True
    CACHE_DIR = Path('cache')
    CACHE_TTL_HOURS = 168
    CACHE_MAX_SIZE = 1000
    
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = 'logs/integrated_pipeline.log'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    MIN_CONFIDENCE_SCORE = 0.5
    HIGH_CONFIDENCE_SCORE = 0.8
    
    BATCH_SIZE = 1000
    SLEEP_SEC = 0.05
    
    # Google Cloud Storage (replaces Drive)
    GCS_BUCKET = os.getenv('GCS_BUCKET', 'ntlr')
    
    # Legacy Drive config (kept for backward compatibility)
    DRIVE_FOLDER_CURRENT = 'NTLR_2025_Raw_Data'
    DRIVE_FOLDER_HISTORICAL = 'NTLR_Historical_Data'
    DOWNLOAD_FOLDER = 'downloads'
    
    NTLR_RURAL_THRESHOLD = 8.689
    NTLR_METRO_THRESHOLD = 88.284
    
    BUFFER_WEIGHTS = {500: 0.70, 1000: 0.17, 1500: 0.07, 2000: 0.06}
    BUFFER_DISTANCES = [500, 1000, 1500, 2000]
    HISTORICAL_BUFFER = 500
    HISTORICAL_YEARS = list(range(2020, 2026))
    
    @classmethod
    def validate(cls):
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if cls.LOG_FILE:
            Path(cls.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        return True
    
    @classmethod
    def get_autocomplete_params(cls, input_text, **kwargs):
        return {
            'input': input_text,
            'key': cls.GOOGLE_API_KEY,
            'components': f'country:{cls.DEFAULT_REGION}',
            'language': kwargs.get('language', cls.DEFAULT_LANGUAGE)
        }
    
    @classmethod
    def get_validation_payload(cls, address):
        return {
            'address': {
                'regionCode': cls.DEFAULT_REGION,
                'addressLines': [address]
            },
            'enableUspsCass': False
        }
    
    @classmethod
    def get_geocoding_params(cls, **kwargs):
        params = {
            'key': cls.GOOGLE_API_KEY,
            'region': cls.DEFAULT_REGION,
            'language': kwargs.get('language', cls.DEFAULT_LANGUAGE)
        }
        if 'address' in kwargs:
            params['address'] = kwargs['address']
        elif 'place_id' in kwargs:
            params['place_id'] = kwargs['place_id']
        elif 'components' in kwargs:
            params['components'] = kwargs['components']
        return params
    
    @classmethod
    def is_within_india(cls, lat, lon):
        return (cls.INDIA_BOUNDS['lat_min'] <= lat <= cls.INDIA_BOUNDS['lat_max'] and
                cls.INDIA_BOUNDS['lon_min'] <= lon <= cls.INDIA_BOUNDS['lon_max'])

try:
    Config.validate()
except ValueError as e:
    import warnings
    warnings.warn(f"Configuration validation failed: {e}")
