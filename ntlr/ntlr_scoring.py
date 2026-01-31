import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config
import pandas as pd
import numpy as np
from scipy.stats import linregress
import os

BUFFER_WEIGHTS = Config.BUFFER_WEIGHTS

def load_csv_batches(folder, pattern):
    """Load all CSVs in folder matching prefix pattern"""
    files = [f for f in os.listdir(folder) if f.startswith(pattern)]
    if not files:
        raise FileNotFoundError(f"No files matching '{pattern}' in folder '{folder}'")
    df = pd.concat([pd.read_csv(os.path.join(folder, f)) for f in files], ignore_index=True)
    print(f"✅ Loaded {len(df)} rows from {len(files)} file(s)")
    return df

def weighted_avg(group, col):
    """Compute buffer-weighted average for a column"""
    return sum(float(r[col]) * BUFFER_WEIGHTS.get(int(r['buffer_m']), 0) for _, r in group.iterrows())

def calculate_ntlr(raw_df, hist_df):
    """Compute NTLR scores for a batch"""
    
    # Rename raw columns for standardization
    raw_df = raw_df.rename(columns={
        'avg_rad_mean': 'mean',
        'avg_rad_median': 'median',
        'avg_rad_mode': 'mode',
        'avg_rad_stdDev': 'stddev',
        'avg_rad_max': 'max',
        'avg_rad_p25': 'p25',
        'avg_rad_p75': 'p75'
    })
    raw_df['buffer_m'] = raw_df['buffer_m'].astype(int)
    
    # CRITICAL: Deduplicate to prevent double-counting if ID appears multiple times
    raw_df = raw_df.drop_duplicates(subset=['id', 'buffer_m'])
    hist_df = hist_df.drop_duplicates(subset=['id', 'year'])
    
    g = raw_df.groupby('id', sort=False)

    # ---------------- Current weighted metrics ----------------
    avg_mean = g.apply(lambda x: weighted_avg(x, 'mean')).rename('ntlr_2025_avg_mean')
    avg_median = g.apply(lambda x: weighted_avg(x, 'median')).rename('ntlr_2025_avg_median')
    avg_mode = g.apply(lambda x: weighted_avg(x, 'mode')).rename('ntlr_2025_avg_mode')
    avg_std = g['stddev'].mean().rename('ntlr_2025_avg_stddev')

    # ---------------- LCI ----------------
    mean_500 = g.apply(lambda x: x.loc[x['buffer_m']==500,'mean'].iloc[0]).rename('mean_500')
    mean_2000 = g.apply(lambda x: x.loc[x['buffer_m']==2000,'mean'].iloc[0]).rename('mean_2000')

    # ---------------- Volatility / Uniformity ----------------
    lists = g.agg({'mean': list, 'stddev': list, 'p25': list, 'p75': list})
    lists['ntlr_avg_volatility'] = lists.apply(
        lambda r: np.mean([sd/m if m>0 else 0 for sd,m in zip(r['stddev'], r['mean'])]), axis=1)
    lists['ntlr_avg_norm_iqr'] = lists.apply(
        lambda r: np.mean([(p75-p25)/m if m>0 else 0 for p75,p25,m in zip(r['p75'], r['p25'], r['mean'])]), axis=1)

    # ---------------- Merge ----------------
    out = pd.concat([
        avg_mean, avg_median, avg_mode, avg_std, mean_500, mean_2000,
        lists[['ntlr_avg_volatility','ntlr_avg_norm_iqr']]
    ], axis=1).reset_index()

    # ---------------- Spatial Scores ----------------
    out['ntlr_stability'] = (1 - out['ntlr_avg_volatility']).clip(0,1)
    out['ntlr_uniformity'] = (1 - out['ntlr_avg_norm_iqr']).clip(0,1)
    out['ntlr_stddev_penalty'] = np.where(
        out['ntlr_2025_avg_mean']>0, 
        (1 - out['ntlr_2025_avg_stddev']/out['ntlr_2025_avg_mean']).clip(0,1), 
        0
    )
    out['ntlr_lci'] = np.where(out['mean_2000']>0, out['mean_500']/out['mean_2000'], 1.0)
    out['ntlr_spatial_score'] = (out['ntlr_stability'] + out['ntlr_uniformity'] + out['ntlr_stddev_penalty'] + out['ntlr_lci']) * out['mean_500']

    # ---------------- Current Score ----------------
    out['ntlr_current_score'] = (out['ntlr_2025_avg_mean'] + out['ntlr_2025_avg_median'] + out['ntlr_2025_avg_mode'])/3

    # ---------------- Temporal Score ----------------
    hist_df = hist_df.rename(columns={'ntl_historical_mean':'mean'})
    def calc_slope(g):
        if len(g)<2: return 0.0
        return linregress(g['year'], g['mean']).slope
    slope_df = hist_df.groupby('id', sort=False).apply(calc_slope).reset_index(name='ntlr_historical_slope')
    out = out.merge(slope_df, on='id', how='left')
    out['ntlr_temporal_score'] = out['ntlr_historical_slope'] * out['mean_500']

    # ---------------- Final NTLR Score ----------------
    out['ntlr_final_score'] = (0.4*out['ntlr_current_score'] + 0.4*out['ntlr_spatial_score'] + 0.2*out['ntlr_temporal_score'])

    # ---------------- Keep lat/lon ----------------
    loc_df = raw_df[['id','lat','lon']].drop_duplicates(subset='id')
    out = out.merge(loc_df, on='id', how='left')

    # Return essential columns
    return out[['id','lat','lon','ntlr_final_score']]
