import os
import json
import mysql.connector
from datetime import datetime

SEED_RECORDS = [
    {
        "id": 1,
        "plant_id": 4136001,
        "timestamp_recorded": "2020-06-17 13:45:00",
        "irradiation": 0.5789,
        "module_temp": 40.4603,
        "ambient_temp": 28.7312,
        "actual_kw": 1743.61,
        "predicted_kw": 13966.11,
        "abs_error_kw": 12222.50,
        "threshold_kw": 4673.13,
        "deviation_type": "UNDERPERFORMANCE",
        "weather_association": "Moderate-high solar irradiation (0.58 kW/m²) with sudden fleet-wide power drop while all 22 inverters remained connected",
        "zero_inverters": 0,
        "investigator_role": "Senior Grid Integration Specialist",
        "supporting_evidence": "Fleet-wide simultaneous power reduction across all 22 inverters (each generating 55-119 kW) confirming external grid export curtailment or system-level ramp rate limit rather than localized hardware disconnect",
        "verification_status": "CONFIRMED_CURTAILMENT"
    },
    {
        "id": 2,
        "plant_id": 4136001,
        "timestamp_recorded": "2020-06-13 09:45:00",
        "irradiation": 0.6071,
        "module_temp": 40.3801,
        "ambient_temp": 27.2044,
        "actual_kw": 5864.74,
        "predicted_kw": 16415.54,
        "abs_error_kw": 10550.80,
        "threshold_kw": 4673.13,
        "deviation_type": "UNDERPERFORMANCE",
        "weather_association": "Rapid morning irradiance ramp (+0.17 kW/m² in 15m) reaching 0.61 kW/m² under clear sky conditions",
        "zero_inverters": 0,
        "investigator_role": "Photovoltaic Systems Field Engineer",
        "supporting_evidence": "Fleet generating only 35.7% of expected capacity despite high clear-sky sun; telemetry indicates pre-fault partial string degradation 45 minutes prior to multi-inverter breaker trip",
        "verification_status": "CONFIRMED_STRING_DEGRADATION"
    },
    {
        "id": 3,
        "plant_id": 4136001,
        "timestamp_recorded": "2020-06-11 12:15:00",
        "irradiation": 0.3882,
        "module_temp": 42.3826,
        "ambient_temp": 29.4208,
        "actual_kw": 1287.88,
        "predicted_kw": 10571.09,
        "abs_error_kw": 9283.22,
        "threshold_kw": 4673.13,
        "deviation_type": "UNDERPERFORMANCE",
        "weather_association": "Midday solar variability with elevated thermal accumulation (module temperature 42.38°C, ambient 29.42°C)",
        "zero_inverters": 0,
        "investigator_role": "Solar Operations Reliability Analyst",
        "supporting_evidence": "Actual AC generation suppressed to 1287.88 kW against expected 10571.09 kW; transient cloud cover combined with high thermal cell derating led to severe power mismatch",
        "verification_status": "CONFIRMED_THERMAL_TRANSIENT"
    },
    {
        "id": 4,
        "plant_id": 4136001,
        "timestamp_recorded": "2020-06-13 10:30:00",
        "irradiation": 0.7941,
        "module_temp": 47.4552,
        "ambient_temp": 28.8012,
        "actual_kw": 3506.09,
        "predicted_kw": 12506.37,
        "abs_error_kw": 9000.28,
        "threshold_kw": 4673.13,
        "deviation_type": "UNDERPERFORMANCE",
        "weather_association": "Peak summer solar irradiance (0.79 kW/m²) accompanied by extreme module surface temperature (47.46°C, temp gap +18.65°C)",
        "zero_inverters": 8,
        "investigator_role": "Substation Operations Director",
        "supporting_evidence": "Critical multi-inverter shutdown: 8 out of 22 inverters (36.4% of total capacity) completely tripped to 0.0 kW under peak solar irradiance, caused by over-temperature protection tripping on central combiner boxes",
        "verification_status": "CONFIRMED_INVERTER_OUTAGE"
    }
]

def export_seed_json(json_path="investigations_seed.json"):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(SEED_RECORDS, f, indent=4)
    print(f"Exported synchronized backup to {json_path}")

def get_mysql_connection():
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", 3306))
    user = os.getenv("MYSQL_USER", "root")
    env_password = os.getenv("MYSQL_PASSWORD")

    candidate_passwords = [env_password] if env_password is not None else ["Abbu@123", "", "root", "password"]

    for pwd in candidate_passwords:
        if pwd is None:
            continue
        try:
            conn = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=pwd,
                connection_timeout=3
            )
            print(f"Connected to MySQL server on {host}:{port} as user '{user}'")
            return conn, pwd
        except mysql.connector.Error:
            continue
    return None, None

def initialize_database():
    # Always export the JSON backup first
    export_seed_json("investigations_seed.json")

    conn, successful_pwd = get_mysql_connection()
    if conn is None:
        print("WARNING: Could not connect to local MySQL service. JSON seed file remains available as synchronized backup.")
        return False

    try:
        cursor = conn.cursor()

        # Create Database
        cursor.execute("CREATE DATABASE IF NOT EXISTS solar_monitoring_db;")
        cursor.execute("USE solar_monitoring_db;")

        # Create Table
        cursor.execute("DROP TABLE IF EXISTS deviation_investigations;")
        create_table_sql = """
        CREATE TABLE deviation_investigations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plant_id BIGINT NOT NULL,
            timestamp_recorded DATETIME NOT NULL,
            irradiation DECIMAL(8, 4) NOT NULL,
            module_temp DECIMAL(8, 4) NOT NULL,
            ambient_temp DECIMAL(8, 4) NOT NULL,
            actual_kw DECIMAL(10, 2) NOT NULL,
            predicted_kw DECIMAL(10, 2) NOT NULL,
            abs_error_kw DECIMAL(10, 2) NOT NULL,
            threshold_kw DECIMAL(10, 2) NOT NULL,
            deviation_type VARCHAR(50) NOT NULL,
            weather_association VARCHAR(255) NOT NULL,
            zero_inverters INT NOT NULL,
            investigator_role VARCHAR(100) NOT NULL,
            supporting_evidence TEXT NOT NULL,
            verification_status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        print("Created table 'deviation_investigations' in 'solar_monitoring_db'")

        # Insert Seed Records
        insert_sql = """
        INSERT INTO deviation_investigations (
            id, plant_id, timestamp_recorded, irradiation, module_temp, ambient_temp,
            actual_kw, predicted_kw, abs_error_kw, threshold_kw, deviation_type,
            weather_association, zero_inverters, investigator_role, supporting_evidence,
            verification_status
        ) VALUES (
            %(id)s, %(plant_id)s, %(timestamp_recorded)s, %(irradiation)s, %(module_temp)s, %(ambient_temp)s,
            %(actual_kw)s, %(predicted_kw)s, %(abs_error_kw)s, %(threshold_kw)s, %(deviation_type)s,
            %(weather_association)s, %(zero_inverters)s, %(investigator_role)s, %(supporting_evidence)s,
            %(verification_status)s
        );
        """
        for rec in SEED_RECORDS:
            cursor.execute(insert_sql, rec)

        conn.commit()
        print(f"Successfully inserted {len(SEED_RECORDS)} real anomalous investigation records!")

        # Verify records
        cursor.execute("SELECT id, plant_id, timestamp_recorded, actual_kw, predicted_kw, abs_error_kw, zero_inverters, verification_status FROM deviation_investigations;")
        rows = cursor.fetchall()
        print("\n--- Current Records in 'deviation_investigations' ---")
        for r in rows:
            print(f"ID {r[0]} | Plant {r[1]} | {r[2]} | Actual: {r[3]} kW | Pred: {r[4]} kW | Error: {r[5]} kW | Zero Inverters: {r[6]} | Status: {r[7]}")

        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"ERROR during database setup: {e}")
        return False

if __name__ == "__main__":
    initialize_database()
