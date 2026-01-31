import os
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from geocoding.pipeline import GeocodingPipeline
from ntlr.ntl_current import (
    initialize_gee as init_gee_current,
    create_feature_collection as fc_current,
    create_2025_ntl_collection,
    submit_export_to_gcs,
    monitor_task
)
from ntlr.ntl_historical import (
    initialize_gee as init_gee_hist,
    create_feature_collection as fc_hist,
    create_historical_ntl_collection,
    submit_export_to_gcs as submit_hist_gcs,
    monitor_task as monitor_hist
)
from ntlr.ntlr_scoring import load_csv_batches, calculate_ntlr
from google.cloud import storage
from google.oauth2 import service_account
import time

def batch_iterator(df, batch_size):
    total = len(df)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield start, end

def init_gcs_client():
    """Initialize Google Cloud Storage client"""
    if not os.path.exists(Config.SERVICE_ACCOUNT_FILE):
        print(f"\n❌ Error: Google Service Account file '{Config.SERVICE_ACCOUNT_FILE}' not found.")
        print("   Please place your 'credentials.json' file in this directory.")
        sys.exit(1)
        
    creds = service_account.Credentials.from_service_account_file(
        Config.SERVICE_ACCOUNT_FILE
    )
    return storage.Client(credentials=creds, project=creds.project_id)

def download_from_gcs(client, prefix, local_folder):
    """Download all files from GCS bucket with given prefix"""
    os.makedirs(local_folder, exist_ok=True)
    
    bucket = client.bucket(Config.GCS_BUCKET)
    blobs = list(bucket.list_blobs(prefix=prefix))
    
    if not blobs:
        print(f"⚠️ No files found in gs://{Config.GCS_BUCKET}/{prefix}")
        return []
    
    downloaded_files = []
    for blob in blobs:
        # Skip folder markers
        if blob.name.endswith('/'):
            continue
            
        filename = os.path.basename(blob.name)
        local_path = os.path.join(local_folder, filename)
        
        blob.download_to_filename(local_path)
        downloaded_files.append(local_path)
        print(f"✅ Downloaded {filename} from GCS")
    
    return downloaded_files

def classify_ntlr(score):
    if pd.isna(score):
        return None
    elif score < Config.NTLR_RURAL_THRESHOLD:
        return "Rural"
    elif score < Config.NTLR_METRO_THRESHOLD:
        return "Urban"
    else:
        return "Metro"

def main():
    print("="*70)
    print("INTEGRATED NTLR PIPELINE - Production Ready")
    print("="*70)
    
    input_csv = input("Enter input CSV filename: ").strip()
    address_col = input("Enter column name containing addresses: ").strip()
    
    if not os.path.exists(input_csv):
        print(f"❌ Error: File '{input_csv}' not found")
        return
    
    df = pd.read_csv(input_csv)
    print(f"📄 Loaded {len(df)} rows from {input_csv}")
    
    if address_col not in df.columns:
        print(f"❌ Error: Column '{address_col}' not found in CSV")
        print(f"Available columns: {', '.join(df.columns)}")
        return
    
    print("\n" + "="*70)
    print("STEP 1: ADVANCED GEOCODING")
    print("="*70)
    
    pipeline = GeocodingPipeline(use_cache=True)
    geocoded_batches = []
    
    for start, end in batch_iterator(df, Config.BATCH_SIZE):
        batch_df = df.iloc[start:end].copy()
        batch_results = []
        
        print(f"\nProcessing batch {start+1}-{end}...")
        for idx, row in batch_df.iterrows():
            result = pipeline.process(row[address_col])
            
            if result.success:
                batch_results.append({
                    'Address': row[address_col],
                    'Latitude': result.location.latitude,
                    'Longitude': result.location.longitude,
                    'Quality': result.location.quality_score,
                    'Confidence': result.location.confidence,
                    'LocationType': result.location.location_type.value
                })
            else:
                batch_results.append({
                    'Address': row[address_col],
                    'Latitude': None,
                    'Longitude': None,
                    'Quality': 0.0,
                    'Confidence': 0.0,
                    'LocationType': 'FAILED'
                })
            
            time.sleep(Config.SLEEP_SEC)
        
        batch_geocoded = pd.DataFrame(batch_results)
        batch_geocoded.to_csv(f"geocoded_{start+1}_{end}.csv", index=False)
        geocoded_batches.append(batch_geocoded)
        print(f"✅ Batch {start+1}-{end} geocoded and saved")
    
    df_geocoded = pd.concat(geocoded_batches, ignore_index=True)
    df_geocoded = df_geocoded.dropna(subset=['Latitude', 'Longitude'])
    
    success_rate = len(df_geocoded) / len(df) * 100
    print(f"\n✅ Geocoding complete: {len(df_geocoded)}/{len(df)} successful ({success_rate:.1f}%)")
    
    if len(df_geocoded) == 0:
        print("❌ No valid coordinates found. Exiting.")
        return
    
    print("\n" + "="*70)
    print("STEP 2: GOOGLE EARTH ENGINE - CURRENT NTL")
    print("="*70)
    
    init_gee_current(Config.GEE_PROJECT_ID)
    for start, end in batch_iterator(df_geocoded, Config.BATCH_SIZE):
        batch_df = df_geocoded.iloc[start:end]
        fc = fc_current(batch_df)
        fc_2025 = create_2025_ntl_collection(fc)
        task = submit_export_to_gcs(fc_2025, start+1, end)
        monitor_task(task)
    
    print("\n" + "="*70)
    print("STEP 3: GOOGLE EARTH ENGINE - HISTORICAL NTL")
    print("="*70)
    
    init_gee_hist(Config.GEE_PROJECT_ID)
    for start, end in batch_iterator(df_geocoded, Config.BATCH_SIZE):
        batch_df = df_geocoded.iloc[start:end]
        fc = fc_hist(batch_df)
        fc_hist_collection = create_historical_ntl_collection(fc)
        task = submit_hist_gcs(fc_hist_collection, start+1, end)
        monitor_hist(task)
    
    print("\n✅ All GEE batches submitted. Waiting for GCS exports...")
    
    print("\n" + "="*70)
    print("STEP 4: DOWNLOAD FROM GOOGLE CLOUD STORAGE")
    print("="*70)
    
    client = init_gcs_client()
    raw_csvs = download_from_gcs(
        client,
        "current/",
        os.path.join(Config.DOWNLOAD_FOLDER, "current")
    )
    hist_csvs = download_from_gcs(
        client,
        "historical/",
        os.path.join(Config.DOWNLOAD_FOLDER, "historical")
    )
    
    print("\n" + "="*70)
    print("STEP 5: NTLR SCORING")
    print("="*70)
    
    raw_df = load_csv_batches(os.path.join(Config.DOWNLOAD_FOLDER, "current"), "ntl_raw_2025")
    hist_df = load_csv_batches(os.path.join(Config.DOWNLOAD_FOLDER, "historical"), "ntl_historical_2020_2025")
    
    ntlr_df = calculate_ntlr(raw_df, hist_df)
    
    print("\n" + "="*70)
    print("STEP 6: MERGE AND CLASSIFY")
    print("="*70)
    
    df_geocoded['id'] = df_geocoded.apply(lambda r: f"{r['Latitude']}_{r['Longitude']}", axis=1)
    final_df = df_geocoded.merge(ntlr_df, on="id", how="left")
    final_df["ntlr_region"] = final_df["ntlr_final_score"].apply(classify_ntlr)
    
    final_df = final_df[[
        "Address",
        "Latitude",
        "Longitude",
        "Quality",
        "Confidence",
        "LocationType",
        "ntlr_final_score",
        "ntlr_region"
    ]]
    
    output_csv = input_csv.replace(".csv", "_with_ntlr.csv")
    final_df.to_csv(output_csv, index=False)
    
    print("\n" + "="*70)
    print("PIPELINE COMPLETE!")
    print("="*70)
    print(f"📊 Total addresses processed: {len(final_df)}")
    print(f"📊 Rural: {len(final_df[final_df['ntlr_region']=='Rural'])}")
    print(f"📊 Urban: {len(final_df[final_df['ntlr_region']=='Urban'])}")
    print(f"📊 Metro: {len(final_df[final_df['ntlr_region']=='Metro'])}")
    print(f"\n🎉 Final CSV saved as: {output_csv}")

if __name__ == "__main__":
    main()