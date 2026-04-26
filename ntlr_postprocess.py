import pandas as pd

def enrich_features(input_path, output_path):

    df = pd.read_csv(input_path)

    buffers = [500, 1000, 1500, 2000]

    for b in buffers:
        df[f"variance_{b}"] = df[f"stdDev_{b}"] ** 2
        df[f"range_{b}"] = df[f"max_{b}"] - df[f"min_{b}"]
        df[f"iqr_{b}"] = df[f"p75_{b}"] - df[f"p25_{b}"]
        df[f"cv_{b}"] = df[f"stdDev_{b}"] / df[f"mean_{b}"]

    df.to_csv(output_path, index=False)

    print(f"✅ Enriched file saved → {output_path}")