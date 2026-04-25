import ee
import pandas as pd
import numpy as np
from scipy.stats import linregress
import time
from tqdm import tqdm
import os
import json

# ================= CONFIG =================
PROJECT_ID = "incomeestimationcase-468413"

BUFFER_DISTANCES = [500, 1000, 1500, 2000]
YEARS = list(range(2020, 2026))

BUFFER_WEIGHTS = {
    500: 0.70,
    1000: 0.17,
    1500: 0.07,
    2000: 0.06
}

OUTPUT_FILE = "ntlr_output_final.csv"
CHECKPOINT_FILE = "ntlr_checkpoint.txt"
PROCESSED_FILE = "ntlr_processed.json"

EPS = 1e-6
# ==========================================


# ================= INIT ===================
def initialize_gee():
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=PROJECT_ID)
    print("✅ GEE Initialized")


# ================= CHECKPOINT =================
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return int(f.read().strip())
    return 0


def save_checkpoint(idx):
    tmp = CHECKPOINT_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(idx))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHECKPOINT_FILE)


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as f:
            return set(tuple(x) for x in json.load(f))
    return set()


def save_processed(processed):
    tmp = PROCESSED_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(list(processed), f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, PROCESSED_FILE)


# ================= REDUCER =================
def get_reducer():
    return (
        ee.Reducer.mean()
        .combine(ee.Reducer.median(), None, True)
        .combine(ee.Reducer.stdDev(), None, True)
        .combine(ee.Reducer.minMax(), None, True)
        .combine(ee.Reducer.percentile([25, 75]), None, True)
    )


# ================= SAFE GEE FETCH =================
def safe_get(d):
    try:
        return d.getInfo()
    except:
        return None


# ================= CURRENT =================
def get_current_ntl(lat, lon):
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select("avg_rad")

    image = viirs.filterDate("2025-03-01", "2025-04-01").first()
    if image is None:
        return pd.DataFrame()

    point = ee.Geometry.Point([lon, lat])
    reducer = get_reducer()

    results = []

    for dist in BUFFER_DISTANCES:
        stats = safe_get(
            image.reduceRegion(
                reducer=reducer,
                geometry=point.buffer(dist),
                scale=500,
                bestEffort=True
            )
        )

        if stats is None:
            continue

        stats["buffer_m"] = dist
        results.append(stats)

    df = pd.DataFrame(results)

    if df.empty:
        return df

    df = df.rename(columns={
        "avg_rad_mean": "mean",
        "avg_rad_median": "median",
        "avg_rad_stdDev": "stdDev",
        "avg_rad_min": "min",
        "avg_rad_max": "max",
        "avg_rad_p25": "p25",
        "avg_rad_p75": "p75"
    })

    # safe numeric fill
    for c in ["mean", "median", "stdDev", "min", "max", "p25", "p75"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["variance"] = df["stdDev"] ** 2
    df["cv"] = df["stdDev"] / (df["mean"] + EPS)
    df["range"] = df["max"] - df["min"]
    df["iqr"] = df["p75"] - df["p25"]
    df["p10"] = df["min"] + 0.1 * df["range"]
    df["p90"] = df["min"] + 0.9 * df["range"]

    return df


# ================= HISTORICAL =================
def get_historical_ntl(lat, lon):
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select("avg_rad")

    point = ee.Geometry.Point([lon, lat])

    data = []

    for year in YEARS:
        img = viirs.filterDate(f"{year}-03-01", f"{year}-04-01").first()

        if img is None:
            val = 0
        else:
            val = safe_get(
                img.reduceRegion(
                    ee.Reducer.mean(),
                    point.buffer(500),
                    500,
                    bestEffort=True
                ).get("avg_rad")
            ) or 0

        data.append({"year": year, "mean": val})

    df = pd.DataFrame(data)
    df["mean_smooth"] = df["mean"].rolling(3, min_periods=1).mean()
    return df


# ================= FLATTEN =================
def flatten_current_features(df):
    out = {}
    for _, row in df.iterrows():
        b = int(row["buffer_m"])
        for col in [
            "mean", "median", "stdDev", "variance", "cv",
            "p25", "p75", "p10", "p90",
            "min", "max", "range", "iqr"
        ]:
            out[f"{col}_{b}"] = row.get(col, 0)
    return out


# ================= SCORING =================
def compute_ntlr(current_df, hist_df):

    if current_df.empty:
        return (0, 0, 0, 0, 0, 0, 0, 0)

    w = current_df["buffer_m"].map(BUFFER_WEIGHTS)

    current_score = (
        (current_df["mean"] * w).sum() +
        (current_df["median"] * w).sum()
    ) / 2

    mean_500 = current_df[current_df["buffer_m"] == 500]["mean"].values[0]
    mean_2000 = current_df[current_df["buffer_m"] == 2000]["mean"].values[0]

    lci = mean_500 / (mean_2000 + EPS)

    volatility = np.mean(current_df["stdDev"] / (current_df["mean"] + EPS))
    norm_iqr = np.mean(current_df["iqr"] / (current_df["mean"] + EPS))

    stability = max(0, 1 - volatility)
    uniformity = max(0, 1 - norm_iqr)

    spatial_score = (stability + uniformity + lci) * mean_500

    if len(hist_df) > 1:
        slope = linregress(hist_df["year"], hist_df["mean_smooth"]).slope
    else:
        slope = 0

    temporal_score = 50 * np.tanh((slope * mean_500) / 100)

    final_score = max(
        0,
        0.4 * current_score +
        0.4 * spatial_score +
        0.2 * temporal_score
    )

    return (
        current_score,
        spatial_score,
        temporal_score,
        final_score,
        lci,
        stability,
        uniformity,
        mean_500
    )


# ================= REGION =================
def classify_region(mean_500, lci):
    if mean_500 > 40 and lci > 1.2:
        return "Metro"
    elif mean_500 > 20:
        return "Urban"
    elif mean_500 > 10:
        return "Peri-Urban"
    elif mean_500 > 3:
        return "Rural"
    return "Dark"


# ================= MAIN =================
def main():

    initialize_gee()

    df_input = pd.read_csv("location.csv")

    start_idx = load_checkpoint()
    processed = load_processed()

    print(f"🔁 Resuming from index: {start_idx}")

    for idx, row in tqdm(df_input.iloc[start_idx:].iterrows(),
                         total=len(df_input) - start_idx):

        lat, lon = row["Latitude"], row["Longitude"]

        if (lat, lon) in processed:
            continue

        try:
            current_df = get_current_ntl(lat, lon)
            hist_df = get_historical_ntl(lat, lon)

            (
                current_score,
                spatial_score,
                temporal_score,
                final_score,
                lci,
                stability,
                uniformity,
                mean_500
            ) = compute_ntlr(current_df, hist_df)

            region = classify_region(mean_500, lci)

            out = {
                "Latitude": lat,
                "Longitude": lon,
                **flatten_current_features(current_df),

                "current_score": current_score,
                "spatial_score": spatial_score,
                "temporal_score": temporal_score,
                "final_score": final_score,

                "lci": lci,
                "stability": stability,
                "uniformity": uniformity,
                "mean_500": mean_500,
                "region": region
            }

            for _, r in hist_df.iterrows():
                out[f"hist_{int(r['year'])}"] = r["mean"]
                out[f"hist_smooth_{int(r['year'])}"] = r["mean_smooth"]

            pd.DataFrame([out]).to_csv(
                OUTPUT_FILE,
                mode="a",
                header=not os.path.exists(OUTPUT_FILE),
                index=False
            )

            processed.add((lat, lon))
            save_processed(processed)
            save_checkpoint(idx + 1)

        except Exception as e:
            print(f"❌ Error at {lat},{lon}: {e}")

        time.sleep(1)

    print("✅ Completed safely")


if __name__ == "__main__":
    main()