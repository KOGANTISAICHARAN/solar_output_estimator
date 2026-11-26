# 🌞 VoltX Solar Intelligence Platform — Viva Evaluation Cheat Sheet

> **Quick Reference for Deepa Mam & HOD Viva — All exact file names and line numbers below.**

---

## 1. Problem Statement, App Name & 3 Stakeholders

### Reverse-Engineered Problem Statement
> *"Solar power plants generate continuous time-series telemetry (irradiation, module temperature, ambient temperature, inverter AC/DC output) but lack an intelligent layer to distinguish between normal generation variability, weather-driven anomalies, and actual equipment faults. This project builds a full-stack AI platform that uses a calibrated SVR regression model trained on a Kaggle solar generation dataset to predict expected AC power output, automatically detect deviations in an unseen chronological test period, and cross-reference 22-inverter telemetry as physical supporting evidence before classifying any event as an equipment fault."*

### Application Name
**VoltX Solar Power Plant Anomaly & Deviation Intelligence Platform**

### 3 Stakeholder Groups & Their Pages

| Stakeholder | Page | URL |
|---|---|---|
| **Solar Plant Operators** — monitor live telemetry & detect underperformance | `static/index.html` | `/static/index.html` |
| **Renewable Energy Companies** — explore unseen anomalies & inverter evidence | `static/deviations.html` | `/static/deviations.html` |
| **Researchers & Engineering Students** — study ML methodology & simulate physics | `static/research.html` | `/static/research.html` |
| *(Shared)* **Auditors & O&M Leads** — CRUD investigation log via MySQL | `static/investigations.html` | `/static/investigations.html` |

---

## 2. Multi-Page Application (MPA) Architecture

> **Key point to show:** 4 separate `.html` files — NOT a Single Page Application. Each link in the navbar navigates to its own HTML file via a standard `<a href="...">` tag.

### Files to Open

| File | Location | What to show |
|---|---|---|
| `static/index.html` | [`static/index.html`](static/index.html) | Navbar with 4 `<a href="...">` links — proves MPA structure |
| `static/deviations.html` | [`static/deviations.html`](static/deviations.html) | Separate HTML document with its own `<head>`, `<body>`, scripts |
| `static/investigations.html` | [`static/investigations.html`](static/investigations.html) | Separate HTML document |
| `static/research.html` | [`static/research.html`](static/research.html) | Separate HTML document |
| `main.py` lines 456–475 | [`main.py`](main.py#L456-L475) | `app.mount("/static", StaticFiles(...))` — FastAPI serves all 4 HTML files |
| `main.py` line 413 | [`main.py`](main.py#L413-L420) | `GET /` → `RedirectResponse(url="/static/index.html")` — root auto-loads dashboard |

---

## 3. JavaScript fetch() API + Event Handling

### Where to Find It Instantly

Open [`static/app.js`](static/app.js) — the entire file is organized with 3 prominent `EVALUATION CHECKPOINT` banners.

---

### Checkpoint A — Kaggle Unseen Dataset Auto-Fill

**`static/app.js` Line 111** — Look for:
```
// === EVALUATION CHECKPOINT A: Event Handling (addEventListener) + fetch() ===
// ===   API CALL  →  GET /api/kaggle-sample?mode=normal|anomaly             ===
```

| Element | Line | Detail |
|---|---|---|
| `fetchKaggleSample()` function | Line 119 | Async function containing the `fetch()` call |
| `fetch('/api/kaggle-sample?mode=...')` | Line 134 | The actual fetch() API call |
| `initKaggleEventListeners()` | Line 175 | `btnNormal.addEventListener("click", ...)` |
| `btnAnomaly.addEventListener("click", ...)` | Line 183 | Second event listener for anomaly button |

**What to say:** *"When the user clicks 'Fetch Kaggle Normal/Anomaly Unseen Row', the `click` event listener calls `fetchKaggleSample(mode)`, which makes a `fetch()` GET request to `/api/kaggle-sample?mode=normal`. The backend reads `solar_daytime_training_dataset.csv`, filters rows where `DATE_TIME > 2020-06-11 10:00:00` (the chronological split cutoff), and returns a real unseen test row that auto-fills all 9 feature inputs."*

---

### Checkpoint B — Live Solar Weather API (Open-Meteo Geocoding)

**`static/app.js` Line 194** — Look for:
```
// === EVALUATION CHECKPOINT B: Event Handling (addEventListener) + fetch() ===
// ===   API CALLS →  (1) GET geocoding-api.open-meteo.com (Geocoding)       ===
// ===                (2) GET api.open-meteo.com/v1/forecast (Solar Weather)  ===
```

| Element | Line | Detail |
|---|---|---|
| `fetchLiveSolarWeather()` function | Line 201 | Main async function |
| Step A: `fetch(geocoding-api...)` | Line 213 | Geocoding to convert city name → lat/lon |
| Step B: `fetch(api.open-meteo.com...)` | Line 228 | Fetches solar irradiance + ambient temperature |
| `initWeatherEventListeners()` | Line 299 | `btnWeather.addEventListener("click", ...)` |

**What to say:** *"The 'Fetch Live Solar Weather' button's `click` listener calls `fetchLiveSolarWeather()`, which makes two sequential `fetch()` calls: first to Open-Meteo's Geocoding API to get coordinates for any city, then to Open-Meteo's Forecast API to get current solar irradiance and ambient temperature, which are auto-filled into the form."*

---

### Checkpoint C — All 4 MySQL CRUD Operations

**`static/app.js` Line 310** — Look for:
```
// === EVALUATION CHECKPOINT C: Event Handling (addEventListener) + fetch() ===
// ===   ALL 4 MySQL CRUD Operations via FastAPI REST endpoints              ===
```

| Operation | Function | Line | HTTP Method | Endpoint |
|---|---|---|---|---|
| **READ** | `apiGetInvestigations()` | Line 327 | `GET` | `/api/investigations` |
| **CREATE** | `apiCreateInvestigation(payload)` | Line 337 | `POST` | `/api/investigations` |
| **UPDATE** | `apiUpdateInvestigation(id, payload)` | Line 350 | `PUT` | `/api/investigations/:id` |
| **DELETE** | `apiDeleteInvestigation(id)` | Line 364 | `DELETE` | `/api/investigations/:id` |
| Event listener (Save/Log) | `initCrudEventListeners()` | Line 392 | `click` | Calls `apiCreateInvestigation` |
| DOMContentLoaded initialization | `document.addEventListener` | Line 407 | — | Wires up all 4 CRUD listeners |

Also show **`static/investigations.html`** lines 287–444 — the page-level script that calls these functions and renders the CRUD table.

---

## 4. Python MySQL Methods → FastAPI REST Endpoints

> **Key diagram to explain:**
> `MySQL (solar_monitoring_db)` ← `mysql.connector` ← **Python functions** ← `FastAPI route decorators` ← **HTTP requests from browser**

### Open `main.py` and show these exact sections:

#### Python Database Functions (mysql.connector layer)

| Function | Line | SQL Operation | Fallback |
|---|---|---|---|
| `db_read_investigations()` | **Line 168** | `SELECT * FROM deviation_investigations` | Returns `investigations_seed.json` if MySQL unreachable |
| `db_create_investigation(data)` | **Line 201** | `INSERT INTO deviation_investigations (...)` | Appends to JSON fallback |
| `db_update_investigation(id, data)` | **Line 248** | `UPDATE deviation_investigations SET ... WHERE id=?` | Updates JSON fallback |
| `db_delete_investigation(id)` | **Line 315** | `DELETE FROM deviation_investigations WHERE id=?` | Removes from JSON fallback |

#### FastAPI Route Decorators (REST conversion layer)

| Decorator | Line | Calls | HTTP Verb |
|---|---|---|---|
| `@app.get("/api/investigations")` | **Line 795** | `db_read_investigations()` | GET |
| `@app.post("/api/investigations")` | **Line 800** | `db_create_investigation(item.dict())` | POST |
| `@app.put("/api/investigations/{item_id}")` | **Line 806** | `db_update_investigation(item_id, ...)` | PUT |
| `@app.delete("/api/investigations/{item_id}")` | **Line 814** | `db_delete_investigation(item_id)` | DELETE |

**What to say:** *"Each Python function uses `mysql.connector` to connect to `solar_monitoring_db` on `localhost:3306`. The FastAPI route decorator (`@app.get`, `@app.post`, etc.) converts that Python function into a REST API endpoint. If MySQL is unreachable, `get_db_connection()` returns `None` and all 4 functions automatically fall back to `investigations_seed.json` — so the frontend always works."*

**Show the automatic fallback at `main.py` line 168:**
```python
def db_read_investigations():
    conn = get_db_connection()
    if conn is None:              # MySQL unreachable → JSON fallback
        try:
            with open(SEED_JSON_PATH) as f:
                return json.load(f)
        ...
```

---

## 5. Unseen Chronological Test Evaluation & Inverter Evidence

> **Key point:** Our model NEVER labels a deviation as an equipment fault without first cross-referencing Plant 2's 22-inverter telemetry.

### Chronological Split (Prevents Time-Series Data Leakage)

**Show `main.py` line 103:**
```python
unseen_test_df = df_daytime[df_daytime["DATE_TIME"] > "2020-06-11 10:00:00"].copy()
```

| Split | Rows | Dates | Used for |
|---|---|---|---|
| Training (80%) | 2,208 rows | Up to 2020-06-11 10:00:00 | Model training + cross-validation |
| Unseen Test (20%) | **669 rows** | 2020-06-11 10:15 → 2020-06-17 18:30 | Anomaly detection (never seen by model) |

**Show `main.py` lines 103–110:** The backend filters `DATE_TIME > 2020-06-11 10:00:00`, runs the calibration model's `.predict()`, computes `ABS_ERROR_KW`, and compares against the **95th-percentile threshold** (2,168.70 kW for Plant 1, 4,673.13 kW for Plant 2).

### Non-Fault Diagnostic Philosophy (22-Inverter Cross-Reference)

**Show `main.py` lines 627–685 (`GET /api/unseen-anomalies`)** — specifically lines 646–653:
```python
p2_inv_summary = df_p2g.groupby("DATE_TIME").agg(
    TOTAL_INVERTERS=("AC_POWER", "count"),
    ZERO_INVERTERS=("AC_POWER", lambda x: int((x == 0).sum()))
)
eval_df = eval_df.merge(p2_inv_summary, on="DATE_TIME", how="left")
```

**Show `main.py` lines 687–775 (`GET /api/inverter-evidence`)** — the endpoint that provides the ±30-minute inverter timeline for drilldown.

### The 4 Real Anomalous Timestamps in the Unseen Period

| # | Timestamp | Plant | Error | Zero Inverters | Evidence-Based Classification |
|---|---|---|---|---|---|
| 1 | `2020-06-17 13:45:00` | 4136001 | 12,222.50 kW | **0/22** | Fleet-Wide Grid Curtailment (all 22 generating normally) |
| 2 | `2020-06-13 09:45:00` | 4136001 | 10,550.80 kW | **0/22** | Morning ramp rate mismatch / string degradation |
| 3 | `2020-06-11 12:15:00` | 4136001 | 9,283.22 kW | **0/22** | High module temp (42.38°C) + cloud transient |
| 4 | `2020-06-13 10:30:00` | 4136001 | 9,000.28 kW | **8/22 offline** | Confirmed multi-inverter hardware trip (physical evidence) |

**What to say:** *"Only timestamp 4 (`2020-06-13 10:30:00`) is labeled as a hardware fault — because `/api/inverter-evidence` shows 8 of 22 inverters outputting exactly 0.0 kW under 0.79 kW/m² irradiance. For timestamp 1 (`2020-06-17 13:45:00`), all 22 inverters are generating normally (55–119 kW each), so the high prediction error is classified as grid curtailment/throttling, NOT an equipment fault."*

---

## 6. Quick File Map

```
solar power project/
├── main.py                        ← FastAPI backend (829 lines)
│   ├── Line   68  → ANOMALY_THRESHOLDS loaded from model bundle
│   ├── Line  103  → Unseen test filter: DATE_TIME > 2020-06-11 10:00:00
│   ├── Line  168  → db_read_investigations()   (GET CRUD function)
│   ├── Line  201  → db_create_investigation()  (POST CRUD function)
│   ├── Line  248  → db_update_investigation()  (PUT CRUD function)
│   ├── Line  315  → db_delete_investigation()  (DELETE CRUD function)
│   ├── Line  413  → GET / → RedirectResponse to /static/index.html
│   ├── Line  456  → POST /api/predict (9-feature SVR inference)
│   ├── Line  581  → GET /api/kaggle-sample (unseen test auto-fill)
│   ├── Line  627  → GET /api/unseen-anomalies (22-inverter merge)
│   ├── Line  687  → GET /api/inverter-evidence (±30-min timeline)
│   ├── Line  795  → GET    /api/investigations → db_read_investigations()
│   ├── Line  800  → POST   /api/investigations → db_create_investigation()
│   ├── Line  806  → PUT    /api/investigations/:id → db_update_investigation()
│   └── Line  814  → DELETE /api/investigations/:id → db_delete_investigation()
│
├── static/app.js                  ← Shared JS (404 lines)
│   ├── Lines   1–17  → Table of Contents with all VIVA checkpoints
│   ├── Line  111     → EVALUATION CHECKPOINT A (Kaggle fetch)
│   ├── Line  134     → fetch('/api/kaggle-sample?mode=...')
│   ├── Line  175     → initKaggleEventListeners() with addEventListener
│   ├── Line  194     → EVALUATION CHECKPOINT B (Weather fetch)
│   ├── Line  213     → fetch(geocoding-api.open-meteo.com)
│   ├── Line  228     → fetch(api.open-meteo.com/v1/forecast)
│   ├── Line  299     → initWeatherEventListeners() with addEventListener
│   ├── Line  310     → EVALUATION CHECKPOINT C (CRUD fetches)
│   ├── Line  327     → fetch GET  /api/investigations
│   ├── Line  337     → fetch POST /api/investigations
│   ├── Line  350     → fetch PUT  /api/investigations/:id
│   ├── Line  364     → fetch DELETE /api/investigations/:id
│   └── Line  407     → document.addEventListener("DOMContentLoaded") master init
│
├── static/index.html              ← Operator Dashboard (Plant 1 & 2 live estimator)
├── static/deviations.html         ← Unseen anomaly explorer + 22-inverter grid
├── static/investigations.html     ← MySQL CRUD triage portal
├── static/research.html           ← ML methodology + physics simulator
│
├── solar_model_bundle.pkl         ← Trained SVR calibration model + thresholds
├── model_metrics.json             ← Exact notebook R²=0.937, MAE, RMSE scores
├── solar_daytime_training_dataset.csv ← 2,877 rows, 2 plants, 80/20 chrono split
├── Plant_2_Generation_Data.csv    ← 67,698 rows, 22 inverters, 15-min intervals
├── database.sql                   ← MySQL DDL + 4 seed anomaly INSERT statements
├── init_db.py                     ← Runs database.sql + exports investigations_seed.json
├── investigations_seed.json       ← JSON fallback with 4 real anomaly records
├── requirements.txt               ← fastapi, uvicorn, scikit-learn, pandas, numpy, joblib, mysql-connector-python
└── run_server.bat                 ← Double-click to start Uvicorn on port 8000
```

---

## 7. How to Start the Server

### Option A — Double-click (Recommended for Demo)
```
Double-click: run_server.bat
Then open:    http://127.0.0.1:8000/
```

### Option B — Command Line
```powershell
cd "c:\Users\parim\OneDrive\Desktop\solar power project"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Option C — Generate Public URL (for Evaluators)
```powershell
# Terminal 1 — Start the server
uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Create public tunnel via localhost.run (no install needed)
ssh -R 80:127.0.0.1:8000 nokey@localhost.run

# OR via cloudflared (cloudflared.exe is already in this project folder)
.\cloudflared.exe tunnel --url http://127.0.0.1:8000
```
> The tunnel prints a public `https://...` URL in the terminal. Share it with evaluators.

### All 5 App Pages
| Page | Local URL |
|---|---|
| Auto-redirect (Root) | http://127.0.0.1:8000/ |
| Operator Dashboard | http://127.0.0.1:8000/static/index.html |
| Unseen Anomaly Explorer | http://127.0.0.1:8000/static/deviations.html |
| MySQL CRUD Triage | http://127.0.0.1:8000/static/investigations.html |
| Research & ML Sandbox | http://127.0.0.1:8000/static/research.html |
| Interactive API Docs | http://127.0.0.1:8000/docs |
| JSON Status Check | http://127.0.0.1:8000/api/status |

---

## 8. Model Evaluation Scores (For Deepa Mam)

| Evaluation Phase | MAE (kW) | RMSE (kW) | R² |
|---|---|---|---|
| Validation Set (80/20 within train) | 932.44 | 1,892.96 | **0.926** |
| Unseen Chronological Test | 872.39 | 1,625.85 | **0.937** |
| Plant 4135001 (Unseen, day-split) | — | — | **0.993** |
| Plant 4136001 (Unseen, day-split) | — | — | **0.802** |

**95th-Percentile Anomaly Thresholds:**
- Plant 4135001 → **2,168.70 kW**
- Plant 4136001 → **4,673.13 kW**

**Result:** 16 anomalies detected in 669 unseen rows (2.4%) — 2 in Plant 1, 14 in Plant 2.
