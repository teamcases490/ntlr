## ⚙️ Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/teamcases490/ntlr.git
cd ntlr
```

---

### 2. Run Setup Script (Windows)

```bash
ntlr_setup.bat
```

---

### 3. Activate Virtual Environment

```bash
venv\Scripts\activate
```

---

### 4. Authenticate Google Earth Engine (First Time Only)

```bash
python -c "import ee; ee.Authenticate()"
```

---

### 5. Run the Pipeline

```bash
python ntlr_pipeline_v1.py
```

---

## 🚀 One-Shot Setup (All Steps Together)

```bash
git clone https://github.com/teamcases490/ntlr.git
cd ntlr
ntlr_setup.bat
venv\Scripts\activate
python -c "import ee; ee.Authenticate()"
python ntlr_pipeline_v1.py
```

---

## 📌 Important Notes

- Run all commands **inside the project folder (`ntlr`)**
- Authentication is needed **only once per machine**
- Ensure `location.csv` is present before running pipeline

---
