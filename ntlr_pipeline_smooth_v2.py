import ee
import pandas as pd
import numpy as np
from scipy.stats import linregress
import time
from tqdm import tqdm
import os

# ================= CONFIG =================
PROJECT_ID = "incomeestimationcase-468413"
OUTPUT_FILE = "ntlr_output_smooth_v2_full.csv"

BUFFER_DISTANCES = [500, 1000, 1500, 2000]
YEARS = list(range(2020, 2026))

BUFFER_WEIGHTS = {
    500: 0.70,
    1000: 0.17,
    1500: 0.07,
    2000: 0.06
}

EPS = 1e-6
# ==========================================


# ================= INIT ===================
def initialize_gee():
    try:
        ee.Initialize(project=PROJECT_ID)
    except:
        ee.Authenticate()
        ee.Initialize(project=PROJECT_ID)
    print("✅ GEE Initialized")


# ================= REDUCER =================
def get_reducer():
    return ee.Reducer.mean() \
        .combine(ee.Reducer.median(), None, True) \
        .combine(ee.Reducer.mode(), None, True) \
        .combine(ee.Reducer.minMax(), None, True) \
        .combine(ee.Reducer.stdDev(), None, True) \
        .combine(ee.Reducer.percentile([25, 75]), None, True)


# ================= CURRENT =================
def get_current_ntl(lat, lon):
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select('avg_rad')
    image = viirs.filterDate('2025-03-01', '2025-04-01').first()

    point = ee.Geometry.Point([lon, lat])
    reducer = get_reducer()

    results = []

    for dist in BUFFER_DISTANCES:
        stats = image.reduceRegion(
            reducer=reducer,
            geometry=point.buffer(dist),
            scale=500,
            bestEffort=True
        ).getInfo()

        stats['buffer_m'] = dist
        results.append(stats)

    df = pd.DataFrame(results)

    # rename base stats
    df = df.rename(columns={
        'avg_rad_mean': 'mean',
        'avg_rad_median': 'median',
        'avg_rad_mode': 'mode',
        'avg_rad_stdDev': 'stdDev',
        'avg_rad_p25': 'p25',
        'avg_rad_p75': 'p75',
        'avg_rad_min': 'min',
        'avg_rad_max': 'max'
    })

    # ================= EXTENDED FEATURES =================
    df["variance"] = df["stdDev"] ** 2
    df["cv"] = df["stdDev"] / (df["mean"] + EPS)

    df["range"] = df["max"] - df["min"]
    df["iqr"] = df["p75"] - df["p25"]

    df["p10"] = df["min"] + 0.1 * (df["max"] - df["min"])
    df["p90"] = df["min"] + 0.9 * (df["max"] - df["min"])

    return df


# ================= HISTORICAL =================
def get_historical_ntl(lat, lon):
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select('avg_rad')
    point = ee.Geometry.Point([lon, lat])

    data = []

    for year in YEARS:
        img = viirs.filterDate(f"{year}-03-01", f"{year}-04-01").first()

        val = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point.buffer(500),
            scale=500,
            bestEffort=True
        ).get('avg_rad')

        val = val.getInfo() if val else 0
        data.append({"year": year, "mean": val})

    df = pd.DataFrame(data)
    df["mean_smooth"] = df["mean"].rolling(3, min_periods=1).mean()

    return df


# ================= FLATTEN =================
def flatten_current_features(current_df):
    out = {}

    for _, row in current_df.iterrows():
        b = int(row["buffer_m"])

        for col in [
            "mean", "median", "mode",
            "stdDev", "variance", "cv",
            "p25", "p75", "p10", "p90",
            "min", "max",
            "range", "iqr"
        ]:
            if col in row:
                out[f"{col}_{b}"] = row[col]

    return out


# ================= SCORING =================
def compute_ntlr(current_df, hist_df):

    def weighted(col):
        weights = current_df['buffer_m'].map(BUFFER_WEIGHTS)
        return float((current_df[col] * weights).sum())

    avg_mean = weighted('mean')
    avg_median = weighted('median')
    avg_mode = weighted('mode')

    current_score = (avg_mean + avg_median + avg_mode) / 3

    mean_500 = current_df[current_df['buffer_m'] == 500]['mean'].values[0]
    mean_2000 = current_df[current_df['buffer_m'] == 2000]['mean'].values[0]

    # ---------- LCI SAFE ----------
    lci = mean_500 / (mean_2000 + EPS)

    # ---------- SPATIAL METRICS SAFE ----------
    volatility = np.mean([
        sd / (m + EPS)
        for sd, m in zip(current_df['stdDev'], current_df['mean'])
    ])

    norm_iqr = np.mean([
        (p75 - p25) / (m + EPS)
        for p75, p25, m in zip(current_df['p75'], current_df['p25'], current_df['mean'])
    ])

    stability = max(0, 1 - volatility)
    uniformity = max(0, 1 - norm_iqr)

    spatial_score = (stability + uniformity + lci) * mean_500

    # ---------- TEMPORAL ----------
    if len(hist_df) >= 2:
        slope = linregress(hist_df['year'], hist_df['mean_smooth']).slope
    else:
        slope = 0

    raw_temporal = slope * mean_500

    # Safer bounded version (recommended)
    temporal_score = 50 * np.tanh(raw_temporal / 100)

    # If you still want hard clipping instead, use:
    # temporal_score = np.clip(raw_temporal, -75, 150)

    final_score = (
        0.4 * current_score +
        0.4 * spatial_score +
        0.2 * temporal_score
    )

    final_score = max(0, final_score)

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
    else:
        return "Dark"


# ================= MAIN =================
def main():
    initialize_gee()

    df_input = pd.read_csv("location.csv")

    if os.path.exists(OUTPUT_FILE):
        df_existing = pd.read_csv(OUTPUT_FILE)
        processed = set(zip(df_existing["Latitude"], df_existing["Longitude"]))
        write_header = False
    else:
        processed = set()
        write_header = True

    for row in tqdm(df_input.itertuples(index=False), total=len(df_input)):
        lat = row.Latitude
        lon = row.Longitude

        if (lat, lon) in processed:
            continue

        try:
            current_df = get_current_ntl(lat, lon)
            hist_df = get_historical_ntl(lat, lon)

            (current_score,
             spatial_score,
             temporal_score,
             final_score,
             lci,
             stability,
             uniformity,
             mean_500) = compute_ntlr(current_df, hist_df)

            region = classify_region(mean_500, lci)

            raw_features = flatten_current_features(current_df)

            out = {
                "Latitude": lat,
                "Longitude": lon,
                **raw_features,
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
                mode='a',
                header=write_header,
                index=False
            )

            write_header = False

        except Exception as e:
            print(f"❌ Error at {lat},{lon}: {e}")

        time.sleep(1)

    print("✅ Completed safely")


if __name__ == "__main__":
    main()