"""Validation against Copernicus EMS (EMSR533), ported from the notebook."""
import datetime as dt
import pathlib

import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.ops import unary_union

from findfire.tracking import STEP

CEMS_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "emsr533"
RESULTS_DIR = pathlib.Path("data") / "results"

PRODUCTS = {
    "Delineation": "2021-08-12 10:40",
    "Monit01": "2021-08-13 10:27",
    "Monit02": "2021-08-14 10:21",
    "Monit03": "2021-08-15 10:12",
    "Monit04": "2021-08-16 10:06",
}
OFFICIAL_HA = {"Delineation": 46361.5, "Monit01": 53094.0, "Monit02": 55337.1,
               "Monit03": 55805.4, "Monit04": 56158.0}


def _find_layers(folder, key):
    return sorted(p for p in folder.rglob("*.shp") if key in p.name.lower())


def load_product(name):
    """Load and merge every area of one product folder -> (observed event gdf, aoi gdf)."""
    folder = CEMS_DIR / name
    ref_fs, aoi_fs = _find_layers(folder, "observedevent"), _find_layers(folder, "areaofinterest")
    if not ref_fs or not aoi_fs:
        found = [p.name for p in folder.rglob("*.shp")]
        raise FileNotFoundError(f"{name}: need 'observedEvent' and 'areaOfInterest' shapefiles. Found: {found}")
    read = lambda fs: pd.concat([gpd.read_file(f).to_crs(4326) for f in fs], ignore_index=True)
    return gpd.GeoDataFrame(read(ref_fs), crs=4326), gpd.GeoDataFrame(read(aoi_fs), crs=4326)


def compare(step, ref, aoi, snap):
    """Overlap between our zone footprints at `step` and the reference, inside the AOI."""
    crs = ref.estimate_utm_crs()
    A = unary_union(aoi.to_crs(crs).geometry)
    R = unary_union(ref.to_crs(crs).geometry).intersection(A)
    z = snap[snap.step == step]
    Z = unary_union(z.to_crs(crs).geometry).intersection(A) if len(z) else A.difference(A)
    inter = Z.intersection(R).area
    union = Z.union(R).area
    return dict(ref_ha=R.area / 1e4, zones_ha=Z.area / 1e4,
                recall=inter / R.area if R.area else np.nan,
                precision=inter / Z.area if Z.area else np.nan,
                iou=inter / union if union else np.nan)


def step_for(obs, step_times):
    """First 12 h step at or after the observation time (last step if later than all steps)."""
    later = step_times[step_times >= obs]
    if len(later):
        return later[0]
    print(f"  warning: {obs} is after the last step; using the last step")
    return step_times[-1]


def run(snap, step_times, data_source, last_data=None):
    """Print the notebook-style validation table and save metrics/area/overlay PNG charts."""
    rows, refs = [], {}
    for name, obs in PRODUCTS.items():
        if not (CEMS_DIR / name).exists():
            print(f"skipping {name}: folder not found"); continue
        obs = pd.Timestamp(obs, tz="UTC")
        if last_data is not None and obs > last_data + STEP:
            print(f"WARNING {name}: FIRMS data ends {last_data:%d %b %H:%M} UTC, before this product.")
        ref, aoi = load_product(name)
        refs[name] = (ref, aoi)
        step = step_for(obs, step_times)
        rows.append(dict(product=name, observed=obs, step=step, ref_official_ha=OFFICIAL_HA.get(name),
                         **compare(step, ref, aoi, snap)))
    if not rows:
        print("No validation possible: no EMSR533 folders found under data/emsr533/")
        return None
    results = pd.DataFrame(rows).round({c: 2 for c in ["ref_ha", "zones_ha", "recall", "precision", "iou"]})
    results["ref_ok"] = ((results.ref_ha / results.ref_official_ha) - 1).abs() < 0.01
    print("\nValidation against Copernicus EMS (EMSR533)")
    print(results.select_dtypes(exclude=["datetime64[ns, UTC]"]).round(2).to_string(index=False))
    if not results.ref_ok.all():
        print("CHECK: ref_ok=False means the loaded files do not match the official burnt area "
              "(wrong folder or missing AOI?).")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_DIR / "emsr_validation.csv", index=False)

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2))
    x = np.arange(len(results)); w = 0.25
    for k, (col, c) in enumerate([("recall", "#2a78d6"), ("precision", "#eb6834"), ("iou", "#1baf7a")]):
        ax[0].bar(x + (k - 1) * w, results[col], w, label=col, color=c)
    ax[0].set_xticks(x); ax[0].set_xticklabels(results["product"]); ax[0].set_ylim(0, 1.05)
    ax[0].set(title="Agreement with Copernicus EMS burned area"); ax[0].legend()
    ax[1].bar(x - w / 2, results.ref_ha, w, label="reference (CEMS)", color="#6c757d")
    ax[1].bar(x + w / 2, results.zones_ha, w, label="our zones", color="#d9632b")
    ax[1].set_xticks(x); ax[1].set_xticklabels(results["product"])
    ax[1].set(title="Burned area (ha), inside the AOI", ylabel="hectares"); ax[1].legend()
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "emsr_metrics.png", dpi=150, bbox_inches="tight")

    name = results["product"].iloc[-1]; ref, aoi = refs[name]
    z_in = gpd.clip(snap[snap.step == results["step"].iloc[-1]], aoi)
    fig2, ax2 = plt.subplots(figsize=(8, 7))
    ref.plot(ax=ax2, color="#2a78d6", alpha=0.35, edgecolor="#2a78d6", linewidth=0.5)
    z_in.plot(ax=ax2, color="#f4a261", alpha=0.45, edgecolor="#e63946", linewidth=1)
    aoi.boundary.plot(ax=ax2, color="black", linewidth=0.8)
    minx, miny, maxx, maxy = aoi.total_bounds
    ax2.set_xlim(minx, maxx); ax2.set_ylim(miny, maxy)
    ax2.legend(handles=[Patch(color="#2a78d6", alpha=0.35, label="CEMS burned area"),
                        Patch(color="#f4a261", alpha=0.5, label="our zones")], loc="lower right")
    ax2.set_title(f"{name}: our zones vs CEMS burned area (inside the AOI)")
    ax2.set_aspect(1 / np.cos(np.radians(36.6)))
    fig2.savefig(RESULTS_DIR / f"emsr_overlay_{name}.png", dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"saved: {RESULTS_DIR / 'emsr_validation.csv'}, {RESULTS_DIR / 'emsr_metrics.png'}, "
          f"{RESULTS_DIR / f'emsr_overlay_{name}.png'}")
    return results