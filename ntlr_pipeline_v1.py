import ee
import pandas as pd
import numpy as np
from scipy.stats import linregress
import time
from tqdm import tqdm
import os

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

OUTPUT_FILE = "ntlr_output_v1_full.csv"
CHECKPOINT_FILE = "ntlr_checkpoint.txt"
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

    return pd.DataFrame(data)


# ================= FLATTEN =================
def flatten_current_features(current_df):
    out = {}

    for _, row in current_df.iterrows():
        b = int(row["buffer_m"])

        for col in ["mean", "median", "mode", "stdDev", "p25", "p75", "min", "max"]:
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

    lci = mean_500 / mean_2000 if mean_2000 else 1

    volatility = np.mean([
        sd/m if m > 0 else 0
        for sd, m in zip(current_df['stdDev'], current_df['mean'])
    ])

    norm_iqr = np.mean([
        (p75-p25)/m if m > 0 else 0
        for p75, p25, m in zip(current_df['p75'], current_df['p25'], current_df['mean'])
    ])

    stability = max(0, 1 - volatility)
    uniformity = max(0, 1 - norm_iqr)

    spatial_score = (stability + uniformity + lci) * mean_500

    slope = linregress(hist_df['year'], hist_df['mean']).slope if len(hist_df) >= 2 else 0

    temporal_score = slope * mean_500

    final_score = (
        0.4 * current_score +
        0.4 * spatial_score +
        0.2 * temporal_score
    )

    return current_score, spatial_score, temporal_score, final_score, lci, stability, uniformity, mean_500


# ================= REGION =================
def classify_region(mean_500, lci):
    if mean_500 > 40 and lci > 1.2:
        return "Urban Core"
    elif mean_500 > 20:
        return "Urban"
    elif mean_500 > 10:
        return "Peri-Urban"
    elif mean_500 > 3:
        return "Rural"
    else:
        return "Dark"


# ================= CHECKPOINT =================
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        return int(open(CHECKPOINT_FILE).read().strip())
    return 0


def save_checkpoint(idx):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(idx))


# ================= MAIN =================
def main():
    initialize_gee()

    df_input = pd.read_csv("location.csv")

    start_idx = load_checkpoint()
    print(f"🔁 Resuming from index: {start_idx}")

    # Load existing output if exists
    if os.path.exists(OUTPUT_FILE):
        df_existing = pd.read_csv(OUTPUT_FILE)
        processed_coords = set(zip(df_existing["Latitude"], df_existing["Longitude"]))
    else:
        df_existing = pd.DataFrame()
        processed_coords = set()

    output_rows = []

    for idx, row in tqdm(
        df_input.iloc[start_idx:].iterrows(),
        total=len(df_input) - start_idx,
        desc="Processing Locations"
    ):
        lat = row["Latitude"]
        lon = row["Longitude"]

        if (lat, lon) in processed_coords:
            continue

        try:
            current_df = get_current_ntl(lat, lon)
            hist_df = get_historical_ntl(lat, lon)

            current_score, spatial_score, temporal_score, final_score, lci, stability, uniformity, mean_500 = compute_ntlr(current_df, hist_df)

            region = classify_region(mean_500, lci)

            raw_features = flatten_current_features(current_df)

            hist_features = {
                f"hist_{int(r['year'])}": r["mean"]
                for _, r in hist_df.iterrows()
            }

            out = {
                "Latitude": lat,
                "Longitude": lon,
                **raw_features,
                **hist_features,
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

            output_rows.append(out)

            # 🔥 SAVE EVERY ROW (CRASH SAFE)
            pd.DataFrame([out]).to_csv(
                OUTPUT_FILE,
                mode='a',
                header=not os.path.exists(OUTPUT_FILE),
                index=False
            )

            save_checkpoint(idx + 1)

        except Exception as e:
            print(f"\n❌ Error at index {idx}: {e}")

        time.sleep(1)

    print("\n✅ Processing complete (safe mode)")


if __name__ == "__main__":
    main()