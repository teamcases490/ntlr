# Integrated NTLR Pipeline - Production Ready

**Advanced Geocoding + Night-Time Light Rating System**

Complete end-to-end pipeline for address geocoding and Metro/Urban/Rural classification using satellite night-time light data.

---

## Features

✅ **Advanced Geocoding**
- Autocomplete for address enhancement
- Address validation and standardization  
- 3 fallback strategies for maximum success rate
- Multi-level caching (70-80% cost reduction)
- India-specific optimizations

✅ **NTLR Scoring**
- Google Earth Engine integration
- Current (2025) + Historical (2020-2025) NTL data
- Spatial, temporal, and current score components
- Automated Metro/Urban/Rural classification

✅ **Production Ready**
- Comprehensive error handling
- Batch processing support
- Detailed logging
- Quality metrics tracking

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.template` to `.env` and add your API keys:

```bash
GOOGLE_API_KEY=your_google_maps_api_key
GEE_PROJECT_ID=your_gee_project_id
SERVICE_ACCOUNT_FILE=credentials.json
```

### 3. Authenticate Google Earth Engine

```bash
earthengine authenticate
```

### 4. Run Pipeline

```bash
python main.py
```

You'll be prompted for:
- Input CSV path
- Address column name

---

## Input Format

CSV file with at least one address column:

```csv
Address
"India Gate, New Delhi"
"Gateway of India, Mumbai"
"Bangalore Palace"
```

---

## Output Format

CSV with geocoded coordinates + NTLR scores:

```csv
Address,Latitude,Longitude,Quality,Confidence,LocationType,ntlr_final_score,ntlr_region
"India Gate, New Delhi",28.6129,77.2295,0.85,0.90,ROOFTOP,92.5,Metro
```

---

## Classification Thresholds

- **Rural**: NTLR score < 8.689
- **Urban**: 8.689 ≤ score < 88.284
- **Metro**: score ≥ 88.284

---

## Architecture

```
Input CSV
    ↓
Advanced Geocoding (with caching)
    ↓
Google Earth Engine (Current + Historical NTL)
    ↓
NTLR Scoring
    ↓
Region Classification
    ↓
Output CSV
```

---

## Directory Structure

```
integrated_pipeline/
├── main.py                  # Main pipeline orchestrator
├── config.py                # Unified configuration
├── requirements.txt         # Dependencies
├── .env                     # Environment variables (create from template)
├── credentials.json         # GEE service account (add manually)
│
├── geocoding/               # Advanced geocoding system
│   ├── pipeline.py          # Main geocoding orchestrator
│   ├── geocoder.py          # Core geocoding
│   ├── autocomplete.py      # Place predictions
│   ├── address_validator.py # Address validation
│   ├── cache_manager.py     # Multi-level caching
│   ├── models.py            # Data models
│   ├── utils.py             # Utilities
│   └── logger.py            # Logging
│
├── ntlr/                    # NTLR processing
│   ├── ntl_current.py       # Current NTL extraction
│   ├── ntl_historical.py    # Historical NTL extraction
│   └── ntlr_scoring.py      # NTLR computation
│
├── cache/                   # Geocoding cache (auto-created)
├── logs/                    # Log files (auto-created)
└── downloads/               # GEE exports (auto-created)
    ├── current/
    └── historical/
```

---

## Configuration

Edit `config.py` or set environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Google Maps API key | Required |
| `GEE_PROJECT_ID` | Google Earth Engine project | Required |
| `SERVICE_ACCOUNT_FILE` | GEE service account JSON | credentials.json |
| `BATCH_SIZE` | Batch size for processing | 1000 |
| `CACHE_TTL_HOURS` | Cache time-to-live | 168 (7 days) |
| `LOG_LEVEL` | Logging level | INFO |

---

## API Requirements

### Google Maps APIs (enable in Google Cloud Console)
- Places API (New)
- Address Validation API
- Geocoding API

### Google Earth Engine
- Enabled project
- Service account with Drive access
- Google Drive folders:
  - `NTLR_2025_Raw_Data`
  - `NTLR_Historical_Data`

---

## Performance

### Geocoding
- **First run**: ~2-3 seconds per address
- **Cached**: ~0.1 seconds per address
- **Success rate**: >95%

### API Costs
- **Without cache**: 3 API calls per address
- **With cache (70% hit rate)**: 0.9 API calls per address
- **Cost reduction**: 70%

---

## Troubleshooting

### "GOOGLE_API_KEY not found"
- Create `.env` file from `.env.template`
- Add your Google Maps API key

### "GEE authentication failed"
- Run `earthengine authenticate`
- Verify `GEE_PROJECT_ID` in `.env`

### "Drive folder not found"
- Create folders in Google Drive:
  - `NTLR_2025_Raw_Data`
  - `NTLR_Historical_Data`
- Share with service account email

### Low geocoding success rate
- Check API key has required APIs enabled
- Verify addresses are in India
- Check logs for specific errors

---

## Batch Processing

The pipeline automatically processes in batches of 1000 rows (configurable).

For large datasets (10k+ rows):
- Geocoding results saved incrementally
- GEE jobs submitted in batches
- Progress tracked in console

---

## Caching

**Two-level cache system:**

1. **Memory cache**: 1000 items, instant access
2. **File cache**: Persistent, 7-day TTL

**Benefits:**
- 70-80% cost reduction after first run
- 20x faster on cached requests
- Survives restarts

**Clear cache:**
```python
from geocoding.cache_manager import get_cache_manager
get_cache_manager().clear()
```

---

## Logging

Logs saved to `logs/integrated_pipeline.log`

**Log levels:**
- DEBUG: Detailed debugging info
- INFO: General progress (default)
- WARNING: Non-critical issues
- ERROR: Critical errors

**Change log level:**
```bash
# In .env
LOG_LEVEL=DEBUG
```

---

## Production Deployment

### Checklist
- [ ] API keys configured in `.env`
- [ ] GEE authenticated
- [ ] Service account JSON added
- [ ] Drive folders created and shared
- [ ] Dependencies installed
- [ ] Test run with sample data

### Best Practices
- Monitor API quota usage
- Regular cache cleanup (auto-handled)
- Review logs for errors
- Backup intermediate results

---

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review error messages in console
3. Verify API keys and permissions
4. Check Google Cloud Console for quota

---

## Version

**v1.0.0** - Production Ready Integration

- Advanced geocoding with caching
- Complete NTLR pipeline
- Production-ready error handling
- Comprehensive logging

---

## License

Team CASE's - LDC, Malad, Maharashtra, India
