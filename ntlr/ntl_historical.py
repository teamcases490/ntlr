import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config
import ee
from datetime import datetime
import time

BUFFER_DISTANCE = Config.HISTORICAL_BUFFER
YEARS = Config.HISTORICAL_YEARS

def initialize_gee(project_id):
    """Authenticate and initialize GEE"""
    try:
        ee.Initialize(project=project_id)
        print(f" GEE initialized for project {project_id}")
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project_id)
        print(f" GEE authenticated and initialized for project {project_id}")

def create_feature_collection(df):
    """Convert DataFrame to GEE FeatureCollection"""
    features = [
        ee.Feature(
            ee.Geometry.Point([row["Longitude"], row["Latitude"]]),
            {
                'id': f"{row['Latitude']}_{row['Longitude']}",
                'lat': row['Latitude'],
                'lon': row['Longitude']
            }
        )
        for _, row in df.iterrows()
    ]
    return ee.FeatureCollection(features)

def create_historical_ntl_collection(fc):
    """Compute historical 2020-2025 March mean NTL at 500 m buffer"""
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select('avg_rad')

    historical_images = [
        viirs.filterDate(f"{year}-03-01", f"{year}-04-01").first()
        for year in YEARS
    ]

    def calc_point_stats(image):
        def map_point(pt):
            geom = pt.geometry().buffer(BUFFER_DISTANCE)
            mean_value = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=500,
                bestEffort=True,
                tileScale=16
            ).get('avg_rad')
            return ee.Feature(None, {
                'id': pt.get('id'),
                'lat': pt.get('lat'),
                'lon': pt.get('lon'),
                'year': ee.Date(image.get('system:time_start')).get('year'),
                'buffer_m': BUFFER_DISTANCE,
                'ntl_historical_mean': mean_value,
                'analysis_type': 'Historical_Mean'
            })
        return fc.map(map_point)

    return ee.ImageCollection(historical_images).map(calc_point_stats).flatten()

def submit_export_to_gcs(fc, start_idx, end_idx):
    """Export FeatureCollection to Google Cloud Storage"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_prefix = f"ntl_historical_2020_2025_{start_idx}_{end_idx}"
    description = f"{file_prefix}_{timestamp}"

    task = ee.batch.Export.table.toCloudStorage(
        collection=fc,
        description=description,
        bucket=Config.GCS_BUCKET,
        fileNamePrefix=f"historical/{file_prefix}",
        fileFormat='CSV'
    )
    task.start()
    print(f" Submitted historical GEE export to GCS: gs://{Config.GCS_BUCKET}/historical/{file_prefix}.csv")
    return task

def monitor_task(task, sleep_sec=30):
    """Wait until GEE task completes"""
    while True:
        status = task.status()['state']
        if status in ["COMPLETED", "FAILED", "CANCELLED"]:
            break
        print(f"⏳ Task {task.status()['description']} status: {status} (waiting {sleep_sec}s)")
        time.sleep(sleep_sec)
    print(f" Task finished with status: {status}")
    return status
