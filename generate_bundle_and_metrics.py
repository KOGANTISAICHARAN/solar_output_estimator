import json
import pickle
import joblib
import pandas as pd
import numpy as np
from sklearn.svm import SVR
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.compose import TransformedTargetRegressor
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def build_model_bundle_and_metrics():
    print("Loading solar_daytime_training_dataset.csv...")
    df = pd.read_csv("solar_daytime_training_dataset.csv")
    print(f"Loaded {df.shape[0]} rows, {df.shape[1]} columns.")

    TARGET = "AC_POWER_PLANT"

    # Preprocessing as established in Untitled31 (2).ipynb (Cells 5, 6, 9, 13)
    df["DATE_TIME"] = pd.to_datetime(df["DATE_TIME"])
    df = df.sort_values(["PLANT_ID", "DATE_TIME"]).reset_index(drop=True)
    df["DATE"] = df["DATE_TIME"].dt.date

    # Drop single-value columns
    same_value = [c for c in df.columns if df[c].nunique() == 1]
    if same_value:
        df = df.drop(columns=same_value)

    # Power per sun and unusual low flag
    df["POWER_PER_SUN"] = df[TARGET] / df["IRRADIATION"]
    low = df.groupby("PLANT_ID")["POWER_PER_SUN"].transform(lambda s: s.quantile(0.01))
    df["UNUSUAL_LOW"] = (df["POWER_PER_SUN"] < low) & (df["IRRADIATION"] > 0.1)

    # Feature engineering: IRR_CHANGE
    gap = df.groupby(["PLANT_ID", "DATE"])["DATE_TIME"].diff()
    change = df.groupby(["PLANT_ID", "DATE"])["IRRADIATION"].diff()
    df["IRR_CHANGE"] = change.where(gap == pd.Timedelta("15min"), 0.0)

    # 9 features
    FEATURES = [
        "IRRADIATION",
        "MODULE_TEMPERATURE",
        "AMBIENT_TEMPERATURE",
        "TEMP_GAP",
        "IRRAD_X_MODTEMP",
        "HOUR_SIN",
        "HOUR_COS",
        "PLANT_ENC",
        "IRR_CHANGE"
    ]

    # Model architecture (SVR inside TransformedTargetRegressor as selected in Step 7 / Cell 15 / Cell 27)
    base_model = TransformedTargetRegressor(
        regressor=make_pipeline(StandardScaler(), SVR(C=10)),
        transformer=StandardScaler()
    )

    # --- Cell 71: Chronological 80/20 train/test split ---
    df = df.sort_values("DATE_TIME").reset_index(drop=True)
    unique_dates = sorted(df["DATE_TIME"].unique())
    cutoff_date = unique_dates[int(len(unique_dates) * 0.80)]

    train_time = df[df["DATE_TIME"] <= cutoff_date].copy()
    test_time = df[df["DATE_TIME"] > cutoff_date].copy()

    X_train_time = train_time[FEATURES]
    y_train_time = train_time[TARGET]

    X_test_time = test_time[FEATURES]
    y_test_time = test_time[TARGET]

    print(f"Chronological split - Training rows: {X_train_time.shape[0]}, Testing rows: {X_test_time.shape[0]}")
    print(f"Training period: {train_time['DATE_TIME'].min()} to {train_time['DATE_TIME'].max()}")
    print(f"Testing period: {test_time['DATE_TIME'].min()} to {test_time['DATE_TIME'].max()}")

    # --- Cell 72: Fresh model on chronological training split ---
    time_model = clone(base_model)
    time_model.fit(X_train_time, y_train_time)
    time_predictions = time_model.predict(X_test_time)

    mae_time = float(mean_absolute_error(y_test_time, time_predictions))
    rmse_time = float(np.sqrt(mean_squared_error(y_test_time, time_predictions)))
    r2_time = float(r2_score(y_test_time, time_predictions))

    print(f"\nTime Model on Test Data (Cell 72):")
    print(f"  MAE:  {mae_time:.3f}")
    print(f"  RMSE: {rmse_time:.3f}")
    print(f"  R2:   {r2_time:.3f}")

    # --- Cell 73: Calibration split (80% model-training, 20% calibration) ---
    train_time = train_time.sort_values("DATE_TIME")
    unique_train_dates = sorted(train_time["DATE_TIME"].unique())
    calibration_cutoff = unique_train_dates[int(len(unique_train_dates) * 0.80)]

    model_training = train_time[train_time["DATE_TIME"] <= calibration_cutoff].copy()
    calibration_data = train_time[train_time["DATE_TIME"] > calibration_cutoff].copy()

    X_model_training = model_training[FEATURES]
    y_model_training = model_training[TARGET]

    X_calibration = calibration_data[FEATURES]
    y_calibration = calibration_data[TARGET]

    calibration_model = clone(base_model)
    calibration_model.fit(X_model_training, y_model_training)

    calibration_predictions = calibration_model.predict(X_calibration)

    calibration_results = pd.DataFrame({
        "PLANT_ENC": calibration_data["PLANT_ENC"].values,
        "ACTUAL": y_calibration.values,
        "PREDICTED": calibration_predictions
    })

    calibration_results["ABS_ERROR"] = (
        calibration_results["ACTUAL"] - calibration_results["PREDICTED"]
    ).abs()

    # 95th percentile anomaly thresholds per plant
    anomaly_thresholds = (
        calibration_results
        .groupby("PLANT_ENC")["ABS_ERROR"]
        .quantile(0.95)
    )

    thresholds_dict = {int(k): float(v) for k, v in anomaly_thresholds.to_dict().items()}
    print("\n95th Percentile Anomaly Thresholds (Cell 73):")
    for plant_enc, th in thresholds_dict.items():
        print(f"  Plant ENC {plant_enc}: {th:.2f} kW")

    # --- Cell 77 & 79: Calibration Model evaluation on unseen chronological test data ---
    final_predictions = calibration_model.predict(X_test_time)
    mae_calib = float(mean_absolute_error(y_test_time, final_predictions))
    rmse_calib = float(np.sqrt(mean_squared_error(y_test_time, final_predictions)))
    r2_calib = float(r2_score(y_test_time, final_predictions))

    print(f"\nFinal Calibration Model on Unseen Chronological Test Data (Cell 79):")
    print(f"  MAE:  {mae_calib:.3f}")
    print(f"  RMSE: {rmse_calib:.3f}")
    print(f"  R2:   {r2_calib:.3f}")

    # Build model bundle matching Cell 80 and specifications
    plant_mapping = {4135001: 0, 4136001: 1}
    model_bundle = {
        "model": calibration_model,
        "calibration_model": calibration_model,
        "features": FEATURES,
        "target": TARGET,
        "plant_mapping": plant_mapping,
        "anomaly_thresholds": thresholds_dict,
        "threshold_percentile": 0.95
    }

    # Save bundle to solar_model_bundle.pkl
    bundle_filename = "solar_model_bundle.pkl"
    with open(bundle_filename, "wb") as f:
        pickle.dump(model_bundle, f)
    print(f"\nSaved model bundle to {bundle_filename}")

    # Export model_metrics.json
    metrics_data = {
        "model_name": "Support Vector Regression (TransformedTargetRegressor)",
        "features": FEATURES,
        "target": TARGET,
        "plant_mapping": plant_mapping,
        "anomaly_thresholds_95th": thresholds_dict,
        "validation": {
            "mae": 932.435,
            "rmse": 1892.959,
            "r2": 0.926,
            "description": "Validation performance on held-out days (Step 8 / Cell 18 & 22 of notebook)"
        },
        "unseen_chronological_test": {
            "mae": round(mae_calib, 3),
            "rmse": round(rmse_calib, 3),
            "r2": round(r2_calib, 3),
            "exact_mae": mae_calib,
            "exact_rmse": rmse_calib,
            "exact_r2": r2_calib,
            "evaluation_period": f"{test_time['DATE_TIME'].min()} to {test_time['DATE_TIME'].max()}",
            "description": "Final calibration model performance on unseen chronological test period (Cell 79 of notebook)"
        },
        "chronological_time_model_test": {
            "mae": round(mae_time, 3),
            "rmse": round(rmse_time, 3),
            "r2": round(r2_time, 3),
            "exact_mae": mae_time,
            "exact_rmse": rmse_time,
            "exact_r2": r2_time,
            "description": "Initial chronological model evaluated on unseen test period (Cell 72 of notebook)"
        },
        "day_split_unseen_test": {
            "mae": 855.308,
            "rmse": 1624.857,
            "r2": 0.939,
            "plant_4135001": {"mae": 463.656, "rmse": 635.929, "r2": 0.993},
            "plant_4136001": {"mae": 1244.367, "rmse": 2204.792, "r2": 0.802},
            "description": "Random day-split test set performance (Cell 18 of notebook)"
        }
    }

    metrics_filename = "model_metrics.json"
    with open(metrics_filename, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=4)
    print(f"Exported metrics to {metrics_filename}")

if __name__ == "__main__":
    build_model_bundle_and_metrics()
