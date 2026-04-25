from ntlr_extractor import run_extraction
from mount_extracted_data_from_drive import wait_for_task, download_latest_file
from ntlr_postprocess import enrich_features

def run_pipeline():

    print("🚀 Running extraction...")
    task = run_extraction()

    print("⏳ Waiting for GEE...")
    wait_for_task(task)

    print("📥 Downloading CSV...")
    file_path = download_latest_file()

    print("⚙️ Enriching features...")
    enrich_features(file_path, file_path.replace(".csv", "_enriched.csv"))

    print("✅ Pipeline complete.")

if __name__ == "__main__":
    run_pipeline()