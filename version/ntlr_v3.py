# =========================================================
# NTLR VERSION 3
# Based on smoothed historical trend + tanh temporal control
# Loads latest enriched dataset from /data
# Outputs: /result/result_v3.csv
# =========================================================

import os
import sys
import pandas as pd
import numpy as np
from scipy.stats import linregress

# =========================================================
# FIX IMPORT PATH (versions/ -> project root)
# =========================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from utils.data_loader import load_latest_dataframe


# ================= CONFIG =================
BUFFER_DISTANCES = [500, 1000, 1500, 2000]

BUFFER_WEIGHTS = {
    500: 0.70,
    1000: 0.17,
    1500: 0.07,
    2000: 0.06
}

YEARS = list(range(2020, 2026))

EPS = 1e-6

RESULT_FOLDER = "result"
RESULT_FILE = "result_v3.csv"


# ================= HELPERS =================
def compute_ntlr_v3_from_row(row):
    # =========================================================
    # CURRENT LAYER
    # =========================================================
    weighted_mean = sum(
        row[f"mean_{b}"] * BUFFER_WEIGHTS[b]
        for b in BUFFER_DISTANCES
    )

    weighted_median = sum(
        row[f"median_{b}"] * BUFFER_WEIGHTS[b]
        for b in BUFFER_DISTANCES
    )

    # V3 current uses mean + median only
    current_score = (
        weighted_mean +
        weighted_median
    ) / 2

    # =========================================================
    # SPATIAL LAYER
    # =========================================================
    mean_500 = row["mean_500"]
    mean_2000 = row["mean_2000"]

    # Light Concentration Index
    lci = mean_500 / (mean_2000 + EPS)

    # Buffer-level volatility
    volatility = np.mean([
        row[f"stdDev_{b}"] / (row[f"mean_{b}"] + EPS)
        for b in BUFFER_DISTANCES
    ])

    # Buffer-level normalized IQR
    norm_iqr = np.mean([
        row[f"iqr_{b}"] / (row[f"mean_{b}"] + EPS)
        for b in BUFFER_DISTANCES
    ])

    # Derived controls
    stability = max(0, 1 - volatility)
    uniformity = max(0, 1 - norm_iqr)

    # Spatial score
    spatial_score = (
        stability +
        uniformity +
        lci
    ) * mean_500

    # =========================================================
    # TEMPORAL LAYER (SMOOTHED)
    # =========================================================
    hist_vals = np.array([
        row[f"hist_{y}"]
        for y in YEARS
    ], dtype=float)

    # Rolling smoothing (3-year moving average)
    hist_smooth = pd.Series(hist_vals).rolling(
        window=3,
        min_periods=1
    ).mean().values

    # Historical slope on smoothed values
    historical_slope = (
        linregress(YEARS, hist_smooth).slope
        if len(hist_smooth) >= 2 else 0
    )

    # Controlled temporal score (prevents extreme spikes)
    temporal_raw = historical_slope * mean_500

    temporal_score = 50 * np.tanh(
        temporal_raw / 100
    )

    # =========================================================
    # FINAL SCORE
    # =========================================================
    final_score = max(
        0,
        (
            0.4 * current_score +
            0.4 * spatial_score +
            0.2 * temporal_score
        )
    )

    # =========================================================
    # RETURN ALL FEATURES
    # =========================================================
    return {
        # Current internals
        "weighted_mean": weighted_mean,
        "weighted_median": weighted_median,

        # Spatial internals
        "lci": lci,
        "volatility": volatility,
        "norm_iqr": norm_iqr,
        "stability": stability,
        "uniformity": uniformity,

        # Temporal internals
        "historical_slope": historical_slope,
        "temporal_raw": temporal_raw,

        # Historical smoothing
        **{
            f"hist_smooth_{year}": hist_smooth[i]
            for i, year in enumerate(YEARS)
        },

        # Final layers
        "current_score": current_score,
        "spatial_score": spatial_score,
        "temporal_score": temporal_score,
        "final_score": final_score
    }


# ================= MAIN =================
def main():
    # Load latest enriched dataset
    df, source_file = load_latest_dataframe()

    print(f"📂 Loaded Source File: {source_file}")
    print("⚙️ Running Version V3 Logic...")

    derived_rows = []

    for _, row in df.iterrows():
        metrics = compute_ntlr_v3_from_row(row)

        # Original dataset + all v3 calculations
        derived_rows.append({
            **row.to_dict(),
            **metrics
        })

    # Final dataframe
    output_df = pd.DataFrame(derived_rows)

    # Ensure result folder
    os.makedirs(RESULT_FOLDER, exist_ok=True)

    # Save result
    output_path = os.path.join(
        RESULT_FOLDER,
        RESULT_FILE
    )

    output_df.to_csv(output_path, index=False)

    print(f"✅ V3 Processing Complete → {output_path}")
    print(f"📊 Rows Processed: {len(output_df)}")
    print(f"📌 Columns Added: {list(metrics.keys())}")


# ================= ENTRY =================
if __name__ == "__main__":
    main()