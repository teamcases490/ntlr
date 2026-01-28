# Quick Reference Guide

## Installation

```bash
cd integrated_pipeline
setup.bat
```

## Configuration

Edit `.env`:
```
GOOGLE_API_KEY=your_key_here
GEE_PROJECT_ID=your_project_id
```

## Run Pipeline

```bash
python main.py
```

## Input Format

CSV with address column:
```csv
Address
"Your address here"
```

## Output Format

CSV with coordinates + NTLR:
```csv
Address,Latitude,Longitude,Quality,Confidence,LocationType,ntlr_final_score,ntlr_region
```

## Classification

- **Rural**: score < 8.689
- **Urban**: 8.689 ≤ score < 88.284  
- **Metro**: score ≥ 88.284

## Troubleshooting

| Issue | Solution |
|-------|----------|
| API key error | Add GOOGLE_API_KEY to .env |
| GEE auth failed | Run `earthengine authenticate` |
| Drive folder not found | Create folders and share with service account |
| Low success rate | Check API quotas and address format |

## Performance

- First run: ~2-3 sec/address
- Cached: ~0.1 sec/address
- Success rate: >95%
- Cost reduction: 70%

## Support

Check `logs/integrated_pipeline.log` for errors
