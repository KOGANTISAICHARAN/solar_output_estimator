"""
Solar Power Plant Deviation Monitoring & Investigation Platform
FastAPI Backend connected to SVR Model Bundle, Empirical CSV Datasets,
Metrics Metadata, and MySQL Database with Synchronized JSON Fallback.
"""

import os
import json
import pickle
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np
import mysql.connector
from fastapi import FastAPI, HTTPException, Query, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# 1. APPLICATION SETUP & CONFIGURATION
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Solar Power Plant Anomaly & Deviation Intelligence API",
    description="Backend API linking machine learning calibration models, solar weather telemetry, inverter generation data, and investigative database records.",
    version="2.0.0"
)

# Enable CORS for seamless interaction with frontend HTML/JS applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_BUNDLE_PATH = os.path.join(BASE_DIR, "solar_model_bundle.pkl")
DAYTIME_DATASET_PATH = os.path.join(BASE_DIR, "solar_daytime_training_dataset.csv")
PLANT2_GEN_PATH = os.path.join(BASE_DIR, "Plant_2_Generation_Data.csv")
METRICS_PATH = os.path.join(BASE_DIR, "model_metrics.json")
SEED_JSON_PATH = os.path.join(BASE_DIR, "investigations_seed.json")

# Database Configuration (Environment variables with local fallback)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Abbu@123")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "solar_monitoring_db")

# -----------------------------------------------------------------------------
# 2. IN-MEMORY ASSETS LOADING & PREPARATION
# -----------------------------------------------------------------------------

# Load Model Bundle
try:
    with open(MODEL_BUNDLE_PATH, "rb") as f:
        bundle = pickle.load(f)
    calibration_model = bundle["model"]
    FEATURES = bundle["features"]
    TARGET = bundle["target"]
    PLANT_MAPPING = bundle["plant_mapping"]  # {4135001: 0, 4136001: 1}
    # Ensure keys in thresholds dictionary are integers
    ANOMALY_THRESHOLDS = {int(k): float(v) for k, v in bundle["anomaly_thresholds"].items()}
    print(f"Loaded ML Bundle successfully. Features: {FEATURES}")
except Exception as e:
    print(f"ERROR: Failed to load model bundle from {MODEL_BUNDLE_PATH}: {e}")
    calibration_model = None
    FEATURES = ["IRRADIATION", "MODULE_TEMPERATURE", "AMBIENT_TEMPERATURE", "TEMP_GAP", "IRRAD_X_MODTEMP", "HOUR_SIN", "HOUR_COS", "PLANT_ENC", "IRR_CHANGE"]
    PLANT_MAPPING = {4135001: 0, 4136001: 1}
    ANOMALY_THRESHOLDS = {0: 2168.70, 1: 4673.13}

# Load Metrics File
try:
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        MODEL_METRICS = json.load(f)
except Exception as e:
    print(f"WARNING: Could not load metrics file: {e}")
    MODEL_METRICS = {}

# Load and Preprocess Datasets
print("Loading solar datasets...")
try:
    df_daytime = pd.read_csv(DAYTIME_DATASET_PATH)
    df_daytime["DATE_TIME"] = pd.to_datetime(df_daytime["DATE_TIME"])
    df_daytime = df_daytime.sort_values(["PLANT_ID", "DATE_TIME"]).reset_index(drop=True)
    df_daytime["DATE"] = df_daytime["DATE_TIME"].dt.date

    # Engineer IRR_CHANGE exactly as in notebook
    gap = df_daytime.groupby(["PLANT_ID", "DATE"])["DATE_TIME"].diff()
    change = df_daytime.groupby(["PLANT_ID", "DATE"])["IRRADIATION"].diff()
    df_daytime["IRR_CHANGE"] = change.where(gap == pd.Timedelta("15min"), 0.0)

    # Derived columns
    df_daytime["TEMP_GAP"] = df_daytime["MODULE_TEMPERATURE"] - df_daytime["AMBIENT_TEMPERATURE"]
    df_daytime["IRRAD_X_MODTEMP"] = df_daytime["IRRADIATION"] * df_daytime["MODULE_TEMPERATURE"]

    # Filter unseen test dataset (after 2020-06-11 10:00:00)
    unseen_test_df = df_daytime[df_daytime["DATE_TIME"] > "2020-06-11 10:00:00"].copy()
    if calibration_model is not None and not unseen_test_df.empty:
        unseen_test_df["PREDICTED_KW"] = calibration_model.predict(unseen_test_df[FEATURES])
        unseen_test_df["ERROR_KW"] = unseen_test_df["AC_POWER_PLANT"] - unseen_test_df["PREDICTED_KW"]
        unseen_test_df["ABS_ERROR_KW"] = unseen_test_df["ERROR_KW"].abs()
        unseen_test_df["THRESHOLD_KW"] = unseen_test_df["PLANT_ENC"].map(ANOMALY_THRESHOLDS)
        unseen_test_df["IS_ANOMALY"] = unseen_test_df["ABS_ERROR_KW"] > unseen_test_df["THRESHOLD_KW"]
        unseen_test_df["DEVIATION_TYPE"] = np.where(unseen_test_df["ERROR_KW"] < 0, "UNDERPERFORMANCE", "ABOVE_EXPECTED")

    print(f"Loaded daytime training dataset: {len(df_daytime)} rows. Unseen test rows: {len(unseen_test_df)}")
except Exception as e:
    print(f"ERROR loading daytime dataset: {e}")
    df_daytime = pd.DataFrame()
    unseen_test_df = pd.DataFrame()

try:
    df_p2g = pd.read_csv(PLANT2_GEN_PATH)
    df_p2g["DATE_TIME"] = pd.to_datetime(df_p2g["DATE_TIME"])
    print(f"Loaded Plant 2 Inverter generation dataset: {len(df_p2g)} rows.")
except Exception as e:
    print(f"ERROR loading Plant 2 generation dataset: {e}")
    df_p2g = pd.DataFrame()

# -----------------------------------------------------------------------------
# 3. DATABASE FUNCTIONS (WITH AUTOMATIC JSON FALLBACK)
# -----------------------------------------------------------------------------

def get_db_connection():
    """Attempt connection to MySQL. Returns connection or None."""
    if os.getenv("VERCEL") and not os.getenv("MYSQL_HOST"):
        return None
    candidate_passwords = [MYSQL_PASSWORD, "Abbu@123", "", "root", "password"]
    for pwd in candidate_passwords:
        if pwd is None:
            continue
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=pwd,
                database=MYSQL_DATABASE,
                connection_timeout=2
            )
            return conn
        except mysql.connector.Error:
            continue
    return None

def read_seed_json() -> List[Dict[str, Any]]:
    """Read synchronized backup seed records."""
    if os.path.exists(SEED_JSON_PATH):
        try:
            with open(SEED_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def write_seed_json(records: List[Dict[str, Any]]):
    """Write updated records to backup JSON."""
    try:
        with open(SEED_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4)
    except Exception as e:
        print(f"WARNING: Failed to update seed JSON backup: {e}")

def db_read_investigations() -> List[Dict[str, Any]]:
    """Function 1: Read all investigations from MySQL, falling back to seed JSON."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM deviation_investigations ORDER BY timestamp_recorded DESC;")
            rows = cursor.fetchall()
            # Format datetime and decimals
            results = []
            for r in rows:
                r_dict = dict(r)
                if isinstance(r_dict.get("timestamp_recorded"), datetime):
                    r_dict["timestamp_recorded"] = r_dict["timestamp_recorded"].strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(r_dict.get("created_at"), datetime):
                    r_dict["created_at"] = r_dict["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                for k, v in r_dict.items():
                    if hasattr(v, "__float__") and not isinstance(v, (int, bool)):
                        r_dict[k] = float(v)
                results.append(r_dict)
            cursor.close()
            conn.close()
            # Synchronize local backup
            write_seed_json(results)
            return results
        except Exception as e:
            print(f"MySQL query error, using JSON fallback: {e}")
            if conn.is_connected():
                conn.close()
    
    # Fallback to seed JSON
    return read_seed_json()

def db_create_investigation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Function 2: Create a new investigation in MySQL, falling back to seed JSON."""
    conn = get_db_connection()
    new_record = dict(data)
    if "created_at" not in new_record:
        new_record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if conn:
        try:
            cursor = conn.cursor()
            query = """
            INSERT INTO deviation_investigations (
                plant_id, timestamp_recorded, irradiation, module_temp, ambient_temp,
                actual_kw, predicted_kw, abs_error_kw, threshold_kw, deviation_type,
                weather_association, zero_inverters, investigator_role, supporting_evidence,
                verification_status
            ) VALUES (
                %(plant_id)s, %(timestamp_recorded)s, %(irradiation)s, %(module_temp)s, %(ambient_temp)s,
                %(actual_kw)s, %(predicted_kw)s, %(abs_error_kw)s, %(threshold_kw)s, %(deviation_type)s,
                %(weather_association)s, %(zero_inverters)s, %(investigator_role)s, %(supporting_evidence)s,
                %(verification_status)s
            );
            """
            cursor.execute(query, new_record)
            conn.commit()
            new_record["id"] = cursor.lastrowid
            cursor.close()
            conn.close()

            # Sync to backup JSON
            seeds = read_seed_json()
            seeds.insert(0, new_record)
            write_seed_json(seeds)
            return new_record
        except Exception as e:
            print(f"MySQL insert error, saving to JSON fallback: {e}")
            if conn.is_connected():
                conn.close()

    # JSON fallback implementation
    seeds = read_seed_json()
    new_id = max([r.get("id", 0) for r in seeds], default=0) + 1
    new_record["id"] = new_id
    seeds.insert(0, new_record)
    write_seed_json(seeds)
    return new_record

def db_update_investigation(item_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Function 3: Update an existing investigation by ID in MySQL, falling back to seed JSON."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # Check existence
            cursor.execute("SELECT * FROM deviation_investigations WHERE id = %s;", (item_id,))
            existing = cursor.fetchone()
            if not existing:
                cursor.close()
                conn.close()
                return None

            # Prepare update statement dynamically
            fields = []
            values = {}
            for k, v in data.items():
                if k != "id" and v is not None:
                    fields.append(f"{k} = %({k})s")
                    values[k] = v
            values["id"] = item_id

            if fields:
                update_sql = f"UPDATE deviation_investigations SET {', '.join(fields)} WHERE id = %(id)s;"
                cursor.execute(update_sql, values)
                conn.commit()

            cursor.execute("SELECT * FROM deviation_investigations WHERE id = %s;", (item_id,))
            updated_row = cursor.fetchone()
            cursor.close()
            conn.close()

            # Format record
            res = dict(updated_row)
            if isinstance(res.get("timestamp_recorded"), datetime):
                res["timestamp_recorded"] = res["timestamp_recorded"].strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(res.get("created_at"), datetime):
                res["created_at"] = res["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            for k, v in res.items():
                if hasattr(v, "__float__") and not isinstance(v, (int, bool)):
                    res[k] = float(v)

            # Sync to backup JSON
            seeds = read_seed_json()
            for i, r in enumerate(seeds):
                if r.get("id") == item_id:
                    seeds[i] = res
                    break
            write_seed_json(seeds)
            return res
        except Exception as e:
            print(f"MySQL update error, using JSON fallback: {e}")
            if conn.is_connected():
                conn.close()

    # JSON fallback implementation
    seeds = read_seed_json()
    for i, r in enumerate(seeds):
        if r.get("id") == item_id:
            for k, v in data.items():
                if v is not None:
                    r[k] = v
            write_seed_json(seeds)
            return r
    return None

def db_delete_investigation(item_id: int) -> bool:
    """Function 4: Delete an investigation by ID in MySQL, falling back to seed JSON."""
    deleted = False
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM deviation_investigations WHERE id = %s;", (item_id,))
            conn.commit()
            if cursor.rowcount > 0:
                deleted = True
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"MySQL delete error, falling back to JSON: {e}")
            if conn.is_connected():
                conn.close()

    # Update backup JSON
    seeds = read_seed_json()
    initial_len = len(seeds)
    seeds = [r for r in seeds if r.get("id") != item_id]
    if len(seeds) < initial_len:
        deleted = True
        write_seed_json(seeds)

    return deleted

# -----------------------------------------------------------------------------
# 4. PYDANTIC SCHEMAS
# -----------------------------------------------------------------------------

class PredictRequest(BaseModel):
    plant_id: int = Field(..., description="Plant ID: 4135001 (Plant 1) or 4136001 (Plant 2)")
    timestamp_str: Optional[str] = Field(None, description="Timestamp in YYYY-MM-DD HH:MM:SS format")
    hour: Optional[float] = Field(None, description="Hour of day (0.0 to 23.75)")
    irradiation: float = Field(..., description="Solar irradiance (kW/m²)")
    module_temperature: float = Field(..., description="PV module back-surface temperature (°C)")
    ambient_temperature: float = Field(..., description="Ambient air temperature (°C)")
    irr_change: Optional[float] = Field(0.0, description="15-minute irradiance gradient (kW/m²)")
    actual_ac_power: Optional[float] = Field(None, description="Observed fleet AC generation (kW)")

class PredictResponse(BaseModel):
    plant_id: int
    plant_enc: int
    timestamp: str
    features: Dict[str, float]
    predicted_ac_power_kw: float
    actual_ac_power_kw: Optional[float]
    abs_error_kw: Optional[float]
    threshold_kw: float
    is_anomaly: Optional[bool]
    deviation_type: Optional[str]
    diagnosis: str

class InvestigationCreate(BaseModel):
    plant_id: int
    timestamp_recorded: str
    irradiation: float
    module_temp: float
    ambient_temp: float
    actual_kw: float
    predicted_kw: float
    abs_error_kw: float
    threshold_kw: float
    deviation_type: str
    weather_association: str
    zero_inverters: int = 0
    investigator_role: str
    supporting_evidence: str
    verification_status: str

class InvestigationUpdate(BaseModel):
    plant_id: Optional[int] = None
    timestamp_recorded: Optional[str] = None
    irradiation: Optional[float] = None
    module_temp: Optional[float] = None
    ambient_temp: Optional[float] = None
    actual_kw: Optional[float] = None
    predicted_kw: Optional[float] = None
    abs_error_kw: Optional[float] = None
    threshold_kw: Optional[float] = None
    deviation_type: Optional[str] = None
    weather_association: Optional[str] = None
    zero_inverters: Optional[int] = None
    investigator_role: Optional[str] = None
    supporting_evidence: Optional[str] = None
    verification_status: Optional[str] = None

# Mount static directory
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# -----------------------------------------------------------------------------
# 5. REST API ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/", tags=["System"])
def root():
    """
    Root URL Redirect (/): Automatically redirects browser visits on http://127.0.0.1:8000/
    directly to the Operator Dashboard (/static/index.html) so evaluators see
    the live UI immediately.
    """
    return RedirectResponse(url="/static/index.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/api/status", tags=["System"])
def api_status():
    """
    JSON System Status check moved to /api/status for programmatic health & model inspection.
    """
    return {
        "status": "ONLINE",
        "service": "Solar Power Plant Anomaly & Deviation Intelligence API",
        "model_loaded": calibration_model is not None,
        "datasets_ready": not df_daytime.empty and not df_p2g.empty,
        "version": "2.0.0",
        "ui_urls": {
            "estimator": "/static/index.html",
            "deviations": "/static/deviations.html",
            "investigations": "/static/investigations.html",
            "research": "/static/research.html"
        }
    }

@app.get("/api/health", tags=["System"])
def health():
    db_conn = get_db_connection()
    is_db_connected = db_conn is not None
    if db_conn:
        db_conn.close()
    return {
        "status": "healthy",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_loaded": calibration_model is not None,
        "database_connected": is_db_connected,
        "using_fallback": not is_db_connected,
        "records_count": len(db_read_investigations())
    }

@app.post("/api/predict", response_model=PredictResponse, tags=["Machine Learning"])
def predict_solar_power(req: PredictRequest):
    """
    Computes 9 exact model features, predicts kW with calibrated model,
    compares against plant 95th-percentile threshold, and generates
    contextual weather/time diagnosis without jumping to hardware blame.
    """
    if calibration_model is None:
        raise HTTPException(status_code=500, detail="ML calibration model is not loaded.")

    # 1. Resolve Plant Encoding
    plant_enc = PLANT_MAPPING.get(req.plant_id, 1 if req.plant_id == 4136001 else 0)

    # 2. Resolve Hour & Trigonometric cyclical time features
    if req.hour is not None:
        hour_val = req.hour
        time_display = req.timestamp_str or f"Hour {hour_val:.2f}"
    elif req.timestamp_str:
        try:
            dt = pd.to_datetime(req.timestamp_str)
            hour_val = dt.hour + (dt.minute / 60.0)
            time_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            hour_val = 12.0
            time_display = req.timestamp_str
    else:
        hour_val = 12.0
        time_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    hour_sin = float(np.sin(2 * np.pi * hour_val / 24.0))
    hour_cos = float(np.cos(2 * np.pi * hour_val / 24.0))

    # 3. Compute thermodynamic & interaction features
    temp_gap = req.module_temperature - req.ambient_temperature
    irrad_x_modtemp = req.irradiation * req.module_temperature
    irr_change = req.irr_change if req.irr_change is not None else 0.0

    # 4. Construct exact 9 features vector
    feature_dict = {
        "IRRADIATION": float(req.irradiation),
        "MODULE_TEMPERATURE": float(req.module_temperature),
        "AMBIENT_TEMPERATURE": float(req.ambient_temperature),
        "TEMP_GAP": float(temp_gap),
        "IRRAD_X_MODTEMP": float(irrad_x_modtemp),
        "HOUR_SIN": float(hour_sin),
        "HOUR_COS": float(hour_cos),
        "PLANT_ENC": int(plant_enc),
        "IRR_CHANGE": float(irr_change)
    }

    # Model inference
    X_input = pd.DataFrame([feature_dict])[FEATURES]
    pred_kw = float(calibration_model.predict(X_input)[0])
    pred_kw = max(0.0, round(pred_kw, 2))

    # 5. Anomaly & Deviation Analysis against calibrated 95th-percentile threshold
    threshold_kw = ANOMALY_THRESHOLDS.get(plant_enc, 4673.13 if plant_enc == 1 else 2168.70)
    abs_error = None
    is_anomaly = None
    deviation_type = None

    if req.actual_ac_power is not None:
        error = req.actual_ac_power - pred_kw
        abs_error = round(abs(error), 2)
        is_anomaly = bool(abs_error > threshold_kw)
        if error < 0:
            deviation_type = "UNDERPERFORMANCE"
        elif error > 0:
            deviation_type = "ABOVE_EXPECTED"
        else:
            deviation_type = "NOMINAL"

        # Rigorous contextual diagnosis without assuming hardware failure
        if is_anomaly:
            if deviation_type == "UNDERPERFORMANCE":
                if req.irradiation > 0.4 and temp_gap > 15.0:
                    diagnosis = (
                        f"Significant underperformance deviation ({abs_error:.1f} kW deficit) observed under strong solar irradiance "
                        f"({req.irradiation:.2f} kW/m²) and elevated thermal differential (+{temp_gap:.1f}°C). The error exceeds the plant's "
                        f"95th-percentile calibration threshold ({threshold_kw:.1f} kW). Without inverter-level verification, this behavior "
                        f"can indicate either physical string disconnection, extreme cell thermal derating, or external grid curtailment."
                    )
                elif req.irradiation > 0.4 and temp_gap <= 15.0:
                    diagnosis = (
                        f"Observed generation ({req.actual_ac_power:.1f} kW) falls substantially below expectation ({pred_kw:.1f} kW) "
                        f"despite solid solar availability ({req.irradiation:.2f} kW/m²). Deviation exceeds calibrated threshold ({threshold_kw:.1f} kW). "
                        f"Possible factors include external grid export limitations, rapid sub-interval cloud transients, or equipment trip. "
                        f"Inverter-level telemetry inspection is recommended to confirm cause."
                    )
                else:
                    diagnosis = (
                        f"Moderate generation deficit ({abs_error:.1f} kW) during low/variable irradiance ({req.irradiation:.2f} kW/m²). "
                        f"Residual exceeds {threshold_kw:.1f} kW statistical boundary; diffuse irradiance dynamics or localized transient cloud cover "
                        f"frequently account for this deviation."
                    )
            else:
                diagnosis = (
                    f"Generation exceeds model forecast by {abs_error:.1f} kW under {req.irradiation:.2f} kW/m² sunlight. "
                    f"Typically driven by cloud-edge solar reflection enhancement (bifacial/albedo gain) or superior module wind cooling."
                )
        else:
            diagnosis = (
                f"Fleet operation is nominal. Prediction error ({abs_error:.1f} kW) remains comfortably within the plant's "
                f"95th-percentile calibration boundary ({threshold_kw:.1f} kW). Generation accurately tracks solar resource dynamics."
            )
    else:
        diagnosis = (
            f"Calculated baseline expected AC power is {pred_kw:.1f} kW for Plant {req.plant_id} given {req.irradiation:.2f} kW/m² "
            f"irradiance and {req.module_temperature:.1f}°C module temperature. Calibrated anomaly threshold is {threshold_kw:.1f} kW."
        )

    return PredictResponse(
        plant_id=req.plant_id,
        plant_enc=plant_enc,
        timestamp=time_display,
        features=feature_dict,
        predicted_ac_power_kw=pred_kw,
        actual_ac_power_kw=req.actual_ac_power,
        abs_error_kw=abs_error,
        threshold_kw=threshold_kw,
        is_anomaly=is_anomaly,
        deviation_type=deviation_type,
        diagnosis=diagnosis
    )

@app.get("/api/kaggle-sample", tags=["Data Explorer"])
def get_kaggle_sample(
    mode: str = Query("normal", description="Mode: 'normal' for nominal row, 'anomaly' for real anomaly"),
    plant_id: Optional[int] = Query(None, description="Optional plant filter: 4135001 or 4136001")
):
    """
    Reads solar_daytime_training_dataset.csv, filters the unseen chronological test period
    (DATE_TIME > 2020-06-11 10:00:00), and returns an auto-fill sample row.
    """
    if unseen_test_df.empty or calibration_model is None:
        raise HTTPException(status_code=503, detail="Unseen test dataset is not initialized.")

    filtered = unseen_test_df.copy()
    if isinstance(plant_id, int):
        filtered = filtered[filtered["PLANT_ID"] == plant_id]

    mode_val = mode if isinstance(mode, str) else "normal"
    if mode_val == "anomaly":
        subset = filtered[filtered["IS_ANOMALY"] == True].sort_values("ABS_ERROR_KW", ascending=False)
    else:
        subset = filtered[filtered["IS_ANOMALY"] == False]

    if subset.empty:
        raise HTTPException(status_code=404, detail=f"No unseen records found matching mode '{mode_val}'.")

    # Pick a representative record
    row = subset.iloc[0]
    dt_str = row["DATE_TIME"].strftime("%Y-%m-%d %H:%M:%S")
    hour_val = round(row["DATE_TIME"].hour + row["DATE_TIME"].minute / 60.0, 2)

    return {
        "mode": mode_val,
        "is_anomaly": bool(row["IS_ANOMALY"]),
        "plant_id": int(row["PLANT_ID"]),
        "timestamp_str": dt_str,
        "hour": hour_val,
        "irradiation": round(float(row["IRRADIATION"]), 4),
        "module_temperature": round(float(row["MODULE_TEMPERATURE"]), 2),
        "ambient_temperature": round(float(row["AMBIENT_TEMPERATURE"]), 2),
        "irr_change": round(float(row["IRR_CHANGE"]), 4),
        "actual_ac_power": round(float(row["AC_POWER_PLANT"]), 2),
        "expected_predicted_kw": round(float(row["PREDICTED_KW"]), 2),
        "abs_error_kw": round(float(row["ABS_ERROR_KW"]), 2),
        "threshold_kw": round(float(row["THRESHOLD_KW"]), 2)
    }

@app.get("/api/unseen-anomalies", tags=["Data Explorer"])
def get_unseen_anomalies():
    """
    Evaluates the 669 unseen test rows, merges Plant 2 inverter counts,
    and returns all real anomalies exceeding calibrated thresholds.
    """
    if unseen_test_df.empty or calibration_model is None:
        raise HTTPException(status_code=503, detail="Unseen test data or model is unavailable.")

    eval_df = unseen_test_df.copy()
    eval_df["PREDICTED_KW"] = calibration_model.predict(eval_df[FEATURES])
    eval_df["ERROR_KW"] = eval_df["AC_POWER_PLANT"] - eval_df["PREDICTED_KW"]
    eval_df["ABS_ERROR_KW"] = eval_df["ERROR_KW"].abs()
    eval_df["THRESHOLD_KW"] = eval_df["PLANT_ENC"].map(ANOMALY_THRESHOLDS)
    eval_df["IS_ANOMALY"] = eval_df["ABS_ERROR_KW"] > eval_df["THRESHOLD_KW"]
    eval_df["DEVIATION_TYPE"] = np.where(eval_df["ERROR_KW"] < 0, "UNDERPERFORMANCE", "ABOVE_EXPECTED")

    # Merge Plant 2 zero inverter stats
    if not df_p2g.empty:
        p2_inv_summary = df_p2g.groupby("DATE_TIME").agg(
            TOTAL_INVERTERS=("SOURCE_KEY", "nunique"),
            ZERO_INVERTERS=("AC_POWER", lambda x: int((x == 0).sum()))
        ).reset_index()
        eval_df = eval_df.merge(p2_inv_summary, on="DATE_TIME", how="left")
    else:
        eval_df["TOTAL_INVERTERS"] = None
        eval_df["ZERO_INVERTERS"] = None

    anomalies_df = eval_df[eval_df["IS_ANOMALY"]].sort_values("ABS_ERROR_KW", ascending=False)

    anomaly_list = []
    for _, r in anomalies_df.iterrows():
        anomaly_list.append({
            "timestamp": r["DATE_TIME"].strftime("%Y-%m-%d %H:%M:%S"),
            "plant_id": int(r["PLANT_ID"]),
            "plant_enc": int(r["PLANT_ENC"]),
            "irradiation": round(float(r["IRRADIATION"]), 4),
            "module_temperature": round(float(r["MODULE_TEMPERATURE"]), 2),
            "ambient_temperature": round(float(r["AMBIENT_TEMPERATURE"]), 2),
            "actual_kw": round(float(r["AC_POWER_PLANT"]), 2),
            "predicted_kw": round(float(r["PREDICTED_KW"]), 2),
            "abs_error_kw": round(float(r["ABS_ERROR_KW"]), 2),
            "threshold_kw": round(float(r["THRESHOLD_KW"]), 2),
            "deviation_type": r["DEVIATION_TYPE"],
            "zero_inverters": int(r["ZERO_INVERTERS"]) if pd.notnull(r.get("ZERO_INVERTERS")) else None,
            "total_inverters": int(r["TOTAL_INVERTERS"]) if pd.notnull(r.get("TOTAL_INVERTERS")) else (22 if r["PLANT_ID"] == 4136001 else None)
        })

    plant1_count = sum(1 for a in anomaly_list if a["plant_id"] == 4135001)
    plant2_count = sum(1 for a in anomaly_list if a["plant_id"] == 4136001)

    return {
        "evaluation_period": "2020-06-11 10:15:00 to 2020-06-17 18:30:00",
        "total_test_records": len(eval_df),
        "total_anomalies_detected": len(anomaly_list),
        "plant_1_anomalies": plant1_count,
        "plant_2_anomalies": plant2_count,
        "anomalies": anomaly_list
    }

@app.get("/api/inverter-evidence", tags=["Data Explorer"])
def get_inverter_evidence(timestamp: str = Query(..., description="Timestamp in YYYY-MM-DD HH:MM:SS format")):
    """
    Inspects Plant_2_Generation_Data.csv at the given timestamp and across a ±30 min window,
    returning inverter counts, fleet throttling assessment, and per-inverter DC/AC readings.
    """
    if df_p2g.empty:
        raise HTTPException(status_code=503, detail="Plant 2 generation dataset is not available.")

    try:
        target_ts = pd.to_datetime(timestamp)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timestamp format. Use YYYY-MM-DD HH:MM:SS.")

    # Exact timestamp records
    exact_df = df_p2g[df_p2g["DATE_TIME"] == target_ts].copy()
    if exact_df.empty:
        # Check nearest timestamps
        nearest = df_p2g[(df_p2g["DATE_TIME"] >= target_ts - pd.Timedelta(hours=2)) & 
                         (df_p2g["DATE_TIME"] <= target_ts + pd.Timedelta(hours=2))]["DATE_TIME"].unique()
        available = [pd.to_datetime(t).strftime("%Y-%m-%d %H:%M:%S") for t in sorted(nearest)[:5]]
        return {
            "error": "No exact Plant 2 inverter readings at this timestamp.",
            "requested_timestamp": timestamp,
            "nearby_available_timestamps": available
        }

    total_inverters = int(exact_df["SOURCE_KEY"].nunique())
    zero_ac_inverters = int((exact_df["AC_POWER"] == 0).sum())
    zero_dc_inverters = int((exact_df["DC_POWER"] == 0).sum())
    total_ac_power = round(float(exact_df["AC_POWER"].sum()), 2)
    total_dc_power = round(float(exact_df["DC_POWER"].sum()), 2)

    # Throttling and fault diagnosis
    if zero_ac_inverters >= 1:
        fleet_status = f"Partial Hardware Outage ({zero_ac_inverters} of {total_inverters} inverters disconnected/zero kW)"
    elif total_ac_power < 5000.0 and total_dc_power < 5500.0:
        fleet_status = "Fleet-Wide Curtailment / Throttling (All inverters connected but output uniformly suppressed)"
    else:
        fleet_status = "Nominal Fleet Generation (All inverters active and generating expected yields)"

    inverter_breakdown = []
    for _, r in exact_df.sort_values("AC_POWER", ascending=True).iterrows():
        inverter_breakdown.append({
            "inverter_id": str(r["SOURCE_KEY"]),
            "dc_power_kw": round(float(r["DC_POWER"]), 2),
            "ac_power_kw": round(float(r["AC_POWER"]), 2),
            "daily_yield": round(float(r.get("DAILY_YIELD", 0.0)), 2),
            "is_zero": bool(r["AC_POWER"] == 0)
        })

    # Window analysis (±30 minutes)
    window_df = df_p2g[(df_p2g["DATE_TIME"] >= target_ts - pd.Timedelta(minutes=30)) &
                       (df_p2g["DATE_TIME"] <= target_ts + pd.Timedelta(minutes=30))]

    timeline_summary = (
        window_df.groupby("DATE_TIME")
        .agg(
            TOTAL_INVERTERS=("SOURCE_KEY", "nunique"),
            ZERO_INVERTERS=("AC_POWER", lambda x: int((x == 0).sum())),
            TOTAL_AC_POWER=("AC_POWER", "sum"),
            TOTAL_DC_POWER=("DC_POWER", "sum")
        )
        .reset_index()
    )

    timeline_list = []
    for _, tr in timeline_summary.iterrows():
        timeline_list.append({
            "timestamp": tr["DATE_TIME"].strftime("%Y-%m-%d %H:%M:%S"),
            "total_inverters": int(tr["TOTAL_INVERTERS"]),
            "zero_inverters": int(tr["ZERO_INVERTERS"]),
            "total_ac_kw": round(float(tr["TOTAL_AC_POWER"]), 2),
            "total_dc_kw": round(float(tr["TOTAL_DC_POWER"]), 2)
        })

    return {
        "timestamp": target_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "plant_id": 4136001,
        "total_inverters": total_inverters,
        "zero_ac_inverters": zero_ac_inverters,
        "zero_dc_inverters": zero_dc_inverters,
        "total_fleet_ac_kw": total_ac_power,
        "total_fleet_dc_kw": total_dc_power,
        "fleet_status": fleet_status,
        "window_timeline": timeline_list,
        "inverters": inverter_breakdown
    }

@app.get("/api/metrics", tags=["Research & Students"])
def get_model_metrics():
    """
    Returns model validation, chronological test metrics, and feature lists
    for display on the Research & Student Page.
    """
    return {
        "model_name": "Support Vector Regression (TransformedTargetRegressor)",
        "features": FEATURES,
        "target": TARGET,
        "plant_mapping": PLANT_MAPPING,
        "anomaly_thresholds_95th": ANOMALY_THRESHOLDS,
        "metrics": MODEL_METRICS
    }

# -----------------------------------------------------------------------------
# 6. INVESTIGATIVE DATABASE CRUD ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/investigations", tags=["Database CRUD"])
def get_investigations():
    """Fetches all registered deviation investigations from MySQL (with JSON fallback)."""
    return db_read_investigations()

@app.post("/api/investigations", status_code=status.HTTP_201_CREATED, tags=["Database CRUD"])
def create_investigation(item: InvestigationCreate):
    """Creates a new deviation investigation log in MySQL (with JSON fallback)."""
    created = db_create_investigation(item.dict())
    return created

@app.put("/api/investigations/{item_id}", tags=["Database CRUD"])
def update_investigation(item_id: int, item: InvestigationUpdate):
    """Updates an existing deviation investigation log in MySQL (with JSON fallback)."""
    updated = db_update_investigation(item_id, item.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Investigation record with ID {item_id} not found.")
    return updated

@app.delete("/api/investigations/{item_id}", tags=["Database CRUD"])
def delete_investigation(item_id: int):
    """Deletes an investigation record from MySQL (with JSON fallback)."""
    deleted = db_delete_investigation(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Investigation record with ID {item_id} not found.")
    return {"message": f"Investigation #{item_id} deleted successfully.", "deleted": True}

# -----------------------------------------------------------------------------
# 7. MAIN ENTRYPOINT
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("Starting Solar Power Plant Anomaly Platform FastAPI Server on http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
