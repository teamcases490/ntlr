import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config
import ee
from datetime import datetime
import time

BUFFER_DISTANCES = Config.BUFFER_DISTANCES

def initialize_gee(project_id):
    """Authenticate and initialize GEE"""
    try:
        ee.Initialize(project=project_id)
        print(f"GEE initialized for project {project_id}")
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project_id)
        print(f"GEE authenticated and initialized for project {project_id}")

def get_reducer():
    """Define multi-stat reducer after GEE is initialized"""
    return ee.Reducer.mean() \
        .combine(ee.Reducer.median(), None, True) \
        .combine(ee.Reducer.mode(), None, True) \
        .combine(ee.Reducer.minMax(), None, True) \
        .combine(ee.Reducer.stdDev(), None, True) \
        .combine(ee.Reducer.percentile([25, 75]), None, True) \
        .combine(ee.Reducer.skew(), None, True) \
        .combine(ee.Reducer.kurtosis(), None, True) \
        .combine(ee.Reducer.count(), None, True)

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

def create_2025_ntl_collection(fc):
    """Compute multi-buffer VIIRS stats for March 2025"""
    REDUCER = get_reducer()
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select('avg_rad')
    image_2025 = viirs.filterDate('2025-03-01', '2025-04-01').first()

    def calc_point_stats(point):
        def map_buffer(dist):
            geom = point.geometry().buffer(dist)
            stats = image_2025.reduceRegion(
                reducer=REDUCER,
                geometry=geom,
                scale=500,
                bestEffort=True,
                tileScale=16
            )
            stats_dict = ee.Dictionary(stats).combine(ee.Dictionary({
                'id': point.get('id'),
                'lat': point.get('lat'),
                'lon': point.get('lon'),
                'buffer_m': dist,
                'year': 2025,
                'analysis_type': '2025_Full'
            }))
            return ee.Feature(None, stats_dict)
        return ee.FeatureCollection(ee.List(BUFFER_DISTANCES).map(map_buffer))

    return fc.map(calc_point_stats).flatten()

def submit_export_to_gcs(fc, start_idx, end_idx):
    """Export FeatureCollection to Google Cloud Storage"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_prefix = f"ntl_raw_2025_{start_idx}_{end_idx}"
    description = f"{file_prefix}_{timestamp}"

    task = ee.batch.Export.table.toCloudStorage(
        collection=fc,
        description=description,
        bucket=Config.GCS_BUCKET,
        fileNamePrefix=f"current/{file_prefix}",
        fileFormat='CSV'
    )
    task.start()
    print(f"Submitted GEE export to GCS: gs://{Config.GCS_BUCKET}/current/{file_prefix}.csv")
    return task

def monitor_task(task, sleep_sec=30):
    """Wait until GEE task completes"""
    while True:
        status = task.status()['state']
        if status in ["COMPLETED", "FAILED", "CANCELLED"]:
            break
        print(f"⏳ Task {task.status()['description']} status: {status} (waiting {sleep_sec}s)")
        time.sleep(sleep_sec)
    print(f"Task finished with status: {status}")
    return status
