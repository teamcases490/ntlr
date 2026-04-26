import os
import sys
import pandas as pd
import numpy as np
from scipy.stats import linregress

# =========================================================
# FIX IMPORT PATH (versions/ -> parent project root)
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

RESULT_FOLDER = "result"
RESULT_FILE = "result_v2.csv"


# ================= HELPERS =================
def compute_ntlr_from_row(row):
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

    # Mode unavailable in enriched set
    weighted_mode = weighted_median

    # NEW (V2): Weighted StdDev
    weighted_stddev = sum(
        row[f"stdDev_{b}"] * BUFFER_WEIGHTS[b]
        for b in BUFFER_DISTANCES
    )

    current_score = (
        weighted_mean +
        weighted_median +
        weighted_mode
    ) / 3

    # =========================================================
    # SPATIAL LAYER
    # =========================================================
    mean_500 = row["mean_500"]
    mean_2000 = row["mean_2000"]

    # Light Concentration Index
    lci = mean_500 / mean_2000 if mean_2000 > 0 else 1.0

    # Average volatility across buffers
    volatility = np.mean([
        row[f"stdDev_{b}"] / (row[f"mean_{b}"] + 1e-6)
        for b in BUFFER_DISTANCES
    ])

    # Average normalized IQR
    norm_iqr = np.mean([
        row[f"iqr_{b}"] / (row[f"mean_{b}"] + 1e-6)
        for b in BUFFER_DISTANCES
    ])

    # Stability / Uniformity
    stability = max(0, 1 - volatility)
    uniformity = max(0, 1 - norm_iqr)

    # NEW (V2): StdDev Penalty
    stddev_penalty = (
        max(0, 1 - (weighted_stddev / (weighted_mean + 1e-6)))
        if weighted_mean > 0 else 0
    )

    # Updated Spatial Score
    spatial_score = (
        stability +
        uniformity +
        stddev_penalty +
        lci
    ) * mean_500

    # =========================================================
    # TEMPORAL LAYER
    # =========================================================
    hist_vals = [
        row[f"hist_{y}"]
        for y in YEARS
    ]

    historical_slope = (
        linregress(YEARS, hist_vals).slope
        if len(hist_vals) >= 2 else 0
    )

    temporal_score = historical_slope * mean_500

    # =========================================================
    # FINAL SCORE
    # =========================================================
    final_score = (
        0.4 * current_score +
        0.4 * spatial_score +
        0.2 * temporal_score
    )

    # =========================================================
    # RETURN ALL FEATURES
    # =========================================================
    return {
        # Weighted raw metrics
        "weighted_mean": weighted_mean,
        "weighted_median": weighted_median,
        "weighted_mode": weighted_mode,
        "weighted_stddev": weighted_stddev,

        # Layer scores
        "current_score": current_score,
        "spatial_score": spatial_score,
        "temporal_score": temporal_score,
        "final_score": final_score,

        # Spatial internals
        "lci": lci,
        "volatility": volatility,
        "norm_iqr": norm_iqr,
        "stability": stability,
        "uniformity": uniformity,
        "stddev_penalty": stddev_penalty,

        # Temporal internals
        "historical_slope": historical_slope
    }


# ================= MAIN =================
def main():
    # Load latest enriched dataset
    df, source_file = load_latest_dataframe()

    print(f"📂 Loaded Source File: {source_file}")
    print("⚙️ Running Version V2 Logic...")

    derived_rows = []

    for _, row in df.iterrows():
        metrics = compute_ntlr_from_row(row)

        # Original + calculated
        derived_rows.append({
            **row.to_dict(),
            **metrics
        })

    # Final dataframe
    output_df = pd.DataFrame(derived_rows)

    # Ensure result folder exists
    os.makedirs(RESULT_FOLDER, exist_ok=True)

    # Output path
    output_path = os.path.join(
        RESULT_FOLDER,
        RESULT_FILE
    )

    # Save
    output_df.to_csv(output_path, index=False)

    print(f"✅ V2 Processing Complete → {output_path}")
    print(f"📊 Rows Processed: {len(output_df)}")
    print(f"📌 Columns Added: {list(metrics.keys())}")


# ================= ENTRY =================
if __name__ == "__main__":
    main()