"""Validation against Copernicus EMS (EMSR533): our zone footprints vs the mapped burned area.

The reference is the burned area Copernicus Emergency Mapping mapped for the August 2021 Kabylie fires
(activation EMSR533, AOI01 Tizi Ouzou). Only meaningful on real FIRMS hotspots: synthetic points carry no burn scar.
Our zones are clipped to each product's area of interest, so fires elsewhere in the study box do not count against us.

    recall    = share of the reference burned area covered by our zones
    precision = share of our zone area that is really burned
    IoU       = overlap over union

Expect high recall and lower precision: our footprints are cumulative and slightly buffered.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.ops import unary_union

from findfire.config import DATA_DIR
from findfire.ingestion.emsr import EMSR_DIR, load_product

RESULTS_DIR = DATA_DIR / "results"

# folder name in data/emsr533/ -> UTC observation time of the post-event image (read from the product map PDF)
PRODUCTS = {
    "Delineation": "2021-08-12 10:40",   # Sentinel-2B, product v2
    "Monit01": "2021-08-13 10:27",       # SPOT 7
    "Monit02": "2021-08-14 10:21",       # SPOT 6
    "Monit03": "2021-08-15 10:12",       # SPOT 7
    "Monit04": "2021-08-16 10:06",       # SPOT 6/7
}
# burnt area (ha) printed on each official map: used to check that the right files were loaded
OFFICIAL_HA = {"Delineation": 46361.5, "Monit01": 53094.0, "Monit02": 55337.1,
               "Monit03": 55805.4, "Monit04": 56158.0}


def step_for(obs, step_times):
    """First 12 h step at or after the observation time (the last step if `obs` is later than all of them)."""
    steps = pd.DatetimeIndex(step_times)
    later = steps[steps >= obs]
    if len(later):
        return later[0]
    print(f"  warning: {obs} is after the last step; using the last step")
    return steps[-1]


def zones_at(snaps, step, min_zone_ha=0.0) -> gpd.GeoDataFrame:
    """Our zones at one tracking step as a lon/lat GeoDataFrame (`snaps` = run_tracking(...)["snaps"]).

    Zones smaller than `min_zone_ha` hectares are dropped. This is a validation-only minimum mapping unit: small
    fires still matter for live alerts, but they are mostly noise when scoring the burned-area extent."""
    zones = next((s["zones"] for s in snaps if s["time"] == step), [])
    zones = [z for z in zones if z["area_ha"] >= min_zone_ha]
    return gpd.GeoDataFrame([dict(zone_id=z["zone_id"], status=z["status"], area_ha=z["area_ha"],
                                  geometry=z["geometry"]) for z in zones], geometry="geometry", crs=4326)


def compare(ref, aoi, zones) -> dict:
    """Overlap between our zones and the reference burned area, inside the area of interest."""
    crs = ref.estimate_utm_crs()
    A = unary_union(aoi.to_crs(crs).geometry)
    R = unary_union(ref.to_crs(crs).geometry).intersection(A)
    Z = unary_union(zones.to_crs(crs).geometry).intersection(A) if len(zones) else A.difference(A)
    inter = Z.intersection(R).area
    union = Z.union(R).area
    return dict(ref_ha=R.area / 1e4, zones_ha=Z.area / 1e4,
                recall=inter / R.area if R.area else np.nan,
                precision=inter / Z.area if Z.area else np.nan,
                iou=inter / union if union else np.nan)


def _plots(results, refs, snaps, out, min_zone_ha=0.0):
    """Two-panel agreement/area chart plus an overlay of our zones on the last product's reference."""
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
    fig.savefig(out / "emsr_metrics.png", dpi=150, bbox_inches="tight")

    name = results["product"].iloc[-1]; ref, aoi = refs[name]
    z_in = gpd.clip(zones_at(snaps, results["step"].iloc[-1], min_zone_ha), aoi)   # only zones inside the AOI
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
    fig2.savefig(out / f"emsr_overlay_{name}.png", dpi=150, bbox_inches="tight")
    plt.close("all")


def validate(res, source="FIRMS", last_data=None, out=None, min_zone_ha=0.0):
    """Compare our tracked zones with every EMSR533 product; print the table and save CSV + PNGs.

    `res` is the run_tracking(...) result. Each product is compared at the first 12 h step at or after its
    observation time. Zones smaller than `min_zone_ha` hectares are ignored (validation-only minimum mapping unit).
    Returns the results DataFrame, or None if nothing could be compared.
    """
    if source and "synthetic" in source.lower():
        print("EMSR validation needs real FIRMS data; this run is synthetic, skipping.")
        return None
    snaps, step_times = res["snaps"], res["steps"]
    if not snaps:
        print("No zones to validate (no hotspots).")
        return None
    out = Path(out or RESULTS_DIR); out.mkdir(parents=True, exist_ok=True)
    rows, refs = [], {}
    for name, obs in PRODUCTS.items():
        if not (EMSR_DIR / name).exists():
            print(f"skipping {name}: folder not found under data/emsr533/"); continue
        obs = pd.Timestamp(obs, tz="UTC")
        if last_data is not None and obs > last_data + pd.Timedelta(hours=12):
            print(f"WARNING {name}: FIRMS data ends {last_data:%d %b %H:%M} UTC, before this product.")
        ref, aoi = load_product(name); refs[name] = (ref, aoi)
        step = step_for(obs, step_times)
        rows.append(dict(product=name, observed=obs, step=step, ref_official_ha=OFFICIAL_HA.get(name),
                         **compare(ref, aoi, zones_at(snaps, step, min_zone_ha))))
    if not rows:
        print("No validation possible: no EMSR533 folders found under data/emsr533/")
        return None
    results = pd.DataFrame(rows).round({c: 2 for c in ["ref_ha", "zones_ha", "recall", "precision", "iou"]})
    results["ref_ok"] = ((results.ref_ha / results.ref_official_ha) - 1).abs() < 0.01   # matches the official area
    print(f"\nValidation against Copernicus EMS (EMSR533), data: {source}"
          + (f" | zones >= {min_zone_ha:g} ha" if min_zone_ha else ""))
    print(results.select_dtypes(exclude=["datetime64[ns, UTC]"]).round(2).to_string(index=False))
    if not results.ref_ok.all():
        print("CHECK: ref_ok=False means the loaded files do not match the official burnt area "
              "(wrong folder or missing AOI?).")
    results.to_csv(out / "emsr_validation.csv", index=False)
    _plots(results, refs, snaps, out, min_zone_ha)
    name = results["product"].iloc[-1]
    print(f"saved: {out / 'emsr_validation.csv'}, {out / 'emsr_metrics.png'}, {out / f'emsr_overlay_{name}.png'}")
    return results
