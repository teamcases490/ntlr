import os
import glob
import pandas as pd


def get_latest_data_file(data_folder="data", keyword="enriched"):
    """
    Finds latest enriched CSV in data folder
    """
    pattern = os.path.join(data_folder, f"*{keyword}*.csv")

    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError("❌ No enriched CSV files found in data/")

    latest_file = max(files, key=os.path.getmtime)

    print(f"📂 Latest file detected: {latest_file}")

    return latest_file


def load_latest_dataframe():
    latest_file = get_latest_data_file()
    df = pd.read_csv(latest_file)

    print(f"✅ Loaded dataframe: {df.shape}")

    return df, latest_file