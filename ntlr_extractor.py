import ee
import pandas as pd

# ================= INIT =================
PROJECT_ID = "incomeestimationcase-468413"

def initialize_gee():
    try:
        ee.Initialize(project=PROJECT_ID)
    except:
        ee.Authenticate()
        ee.Initialize(project=PROJECT_ID)

initialize_gee()

# ================= INPUT =================
df = pd.read_csv("location.csv")

points = ee.FeatureCollection([
    ee.Feature(
        ee.Geometry.Point([row["Longitude"], row["Latitude"]]),
        {"id": i}
    )
    for i, row in df.iterrows()
])

# ================= DATA =================
viirs = ee.ImageCollection(
    "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
).select("avg_rad")

img_2025 = viirs.filterDate("2025-03-01", "2025-04-01").mean()

# ================= CONFIG =================
BUFFERS = [500, 1000, 1500, 2000]

# ================= FEATURE FUNCTION =================
def compute_features(feature):

    geom = feature.geometry()
    props = feature.toDictionary()

    # ✅ ADD EXACT LAT/LON
    coords = geom.coordinates()
    props = props.set("Latitude", coords.get(1))
    props = props.set("Longitude", coords.get(0))

    for b in BUFFERS:

        buffer = geom.buffer(b)

        stats = img_2025.reduceRegion(
            reducer=ee.Reducer.mean()
                .combine(ee.Reducer.median(), '', True)
                .combine(ee.Reducer.stdDev(), '', True)
                .combine(ee.Reducer.minMax(), '', True)
                .combine(ee.Reducer.percentile([25, 75]), '', True),
            geometry=buffer,
            scale=500,
            bestEffort=True
        )

        # ✅ MANUAL SAFE MAPPING
        stats_dict = ee.Dictionary({
            f"mean_{b}": stats.get("avg_rad_mean"),
            f"median_{b}": stats.get("avg_rad_median"),
            f"stdDev_{b}": stats.get("avg_rad_stdDev"),
            f"min_{b}": stats.get("avg_rad_min"),
            f"max_{b}": stats.get("avg_rad_max"),
            f"p25_{b}": stats.get("avg_rad_p25"),
            f"p75_{b}": stats.get("avg_rad_p75"),
        })

        props = ee.Dictionary(props).combine(stats_dict)

    # ================= HISTORICAL =================
    for y in range(2020, 2026):

        val = viirs.filterDate(
            f"{y}-03-01",
            f"{y}-04-01"
        ).mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom.buffer(500),
            scale=500,
            bestEffort=True
        ).get("avg_rad")

        props = props.set(f"hist_{y}", val)

    return ee.Feature(geom, props)


def run_extraction():

    result = points.map(compute_features)

    task = ee.batch.Export.table.toDrive(
        collection=result,
        description="NTLR_BUFFER_FEATURES",
        folder="EarthEngine",
        fileNamePrefix="ntlr_features",
        fileFormat="CSV"
    )

    task.start()

    print("🚀 Export started")
    return task


if __name__ == "__main__":
    run_extraction()