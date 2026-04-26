# 🌍 NTLR Pipeline — Production-Grade Geospatial Nighttime Lights Extraction & Scoring

---

# 🏗️ Architecture

```id="b1o4d4"
location.csv
    ↓
GEE Extraction (VIIRS + Buffers + Historical)
    ↓
Google Drive Export
    ↓
Task Monitoring
    ↓
Auto Download
    ↓
Versioned Processing Logic
    ↓
Final Output
```

---

# 📂 Project Structure

```id="vw8ukw"
ntlr/
│
├── ntlr_extractor.py                   # GEE extraction engine
├── mount_extracted_data_from_drive.py  # Drive auth + task wait + download
├── ntlr_pipeline.py                    # Main CLI pipeline
│
├── config.py                           # Central configuration
├── location.csv                        # Input coordinates
│
├── data/                               # Raw + processed outputs
├── credentials.json                    # Auto-generated after first auth
├── client_secrets.json                 # Google OAuth credentials
│
├── requirements.txt
└── README.md
```

---

# 🚀 Installation

## 1️⃣ Clone Repository

```bash id="bdblmy"
git clone <your_repo_url>
cd ntlr
```

---

## 2️⃣ Create Virtual Environment

### Windows:

```bash id="8pkkqj"
python -m venv venv
venv\Scripts\activate
```

### Mac/Linux:

```bash id="gwj7nc"
python3 -m venv venv
source venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash id="am8h1h"
pip install -r requirements.txt
```

---

# 🔐 Authentication Setup

---

## Google Earth Engine

```bash id="8b0x3n"
earthengine authenticate
```

---

## Google Drive API

### Required:

- Google Cloud Console
- Enable Google Drive API
- OAuth Client ID (Desktop App)

### Place downloaded file as:

```id="x5q4lm"
client_secrets.json
```

---

# ⚙️ Configuration

## `config.py`

```python id="gr5wyw"
PROJECT_ID = "your-gee-project-id"

DEFAULT_PREFIX = "ntlr_features"

DATA_DIR = "data"

DEFAULT_VERSION = "v1"
```

---

# 🖥️ Command Line Usage

---

## Basic Run

```bash id="oqmyq0"
python ntlr_pipeline.py
```

---

## Specify Version

```bash id="6fuy2d"
python ntlr_pipeline.py --version v2
```

---

## Custom Output Prefix

```bash id="k7o1s9"
python ntlr_pipeline.py --prefix my_ntlr_run
```

---

## Skip Extraction (Use Existing File)

```bash id="j53b1w"
python ntlr_pipeline.py --skip-extraction
```

---

# 🧩 CLI Arguments

| Argument            | Description                                 |
| ------------------- | ------------------------------------------- |
| `--version`         | Processing logic version (`v1`, `v2`, etc.) |
| `--prefix`          | Output filename prefix                      |
| `--skip-extraction` | Skip GEE and process latest local file      |
| `--raw-only`        | Only extract + download                     |
| `--debug`           | Verbose logging                             |

---

# 📄 Example

```bash id="2e9m7z"
python ntlr_pipeline.py --version v3 --prefix mumbai_run --debug
```

---

# 🔄 Pipeline Stages

---

## Stage 1: Extraction

**Script:** `ntlr_extractor.py`

### Outputs:

- `mean_500`, `mean_1000`, `mean_1500`, `mean_2000`
- `median`
- `stdDev`
- `variance`
- `IQR`
- `CV`
- `Historical (2020–2025)`

---

## Stage 2: Monitoring

**Script:** `wait_for_task(task)`

Checks:

```id="fxj5um"
READY
RUNNING
COMPLETED
FAILED
```

---

## Stage 3: Download

**Script:** `download_latest_file()`

### Output:

```id="mkb8vi"
data/ntlr_features_<timestamp>.csv
```

---

## Stage 4: Version Processing

**Folder:** `versions/`

### Example:

```python id="1rhhf4"
def run(df):
    df["score"] = df["mean_500"] * 0.4
    return df
```

---

# 🧠 Versioning Philosophy

### Stable:

- Extraction
- Authentication
- Download
- File management

### Variable:

- Scoring
- Feature engineering
- Weighting logic
- ML models

---

# 📝 Logging

Production runs should use:

```python id="8dyy5q"
import logging
logging.basicConfig(level=logging.INFO)
```

### Example:

```id="g0a8vr"
INFO: Extraction started
INFO: Task completed
INFO: Download successful
INFO: Running version v2
INFO: Output saved
```

---

# 🛠️ Common Errors

---

## `ModuleNotFoundError: pydrive2`

```bash id="1gw46g"
pip install pydrive2
```

---

## `client_secrets.json missing`

Place OAuth file in root:

```id="j63m65"
ntlr/client_secrets.json
```

---

## `credentials.json missing`

Occurs only on first run → expected.

---

## `Task FAILED`

Check:

- GEE quota
- Project ID
- Buffer size
- Feature count

---

# 📊 Output Types

| Output File      | Description      |
| ---------------- | ---------------- |
| `*_raw.csv`      | Raw extraction   |
| `*_enriched.csv` | Derived features |
| `*_v1.csv`       | Versioned logic  |
| `*_scored.csv`   | Final score      |

---

# 🔥 Recommended Best Practices

## ✅ Do:

- Keep extraction constant
- Use version modules
- Timestamp outputs
- Maintain checkpoints

## ❌ Avoid:

- Hardcoding versions in pipeline
- Duplicating extraction scripts
- Overwriting outputs

---

# 🧪 Future Roadmap

- [ ] Dynamic version registry
- [ ] YAML config support
- [ ] Parallel chunk processing
- [ ] Checkpoint recovery
- [ ] NTLR scoring integration
- [ ] Road + Amenity + Landscape fusion
- [ ] ML hyperplane scoring

---

# 🤝 Contributing

### New Version Logic:

1. Create file:

```id="e0qqkq"
versions/v4.py
```

2. Add:

```python id="h3m2cl"
def run(df):
    return df
```

3. Execute:

```bash id="9k5v8w"
python ntlr_pipeline.py --version v4
```

---

# 📜 License

MIT License

---

# 👨‍💻 Maintainer

**Earnest Ebenezer**
Geospatial Intelligence • Infrastructure Scoring • NTLR Systems

---
