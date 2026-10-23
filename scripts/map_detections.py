"""Static Leaflet map of detections after the false-alarm filters.

Reads a saved detection CSV (default data/live/viirs.csv), applies the FIRMS
`type` filter plus the curated/static exclusion circles, and writes an HTML map
where the user can pick a date and toggle kept/removed detections.

    python scripts/map_detections.py
    python scripts/map_detections.py --csv data/live/viirs.csv --date 2026-10-22
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from findfire.config import DATA_DIR, STUDY_BBOX
from findfire.detection.filters import (
    apply_exclusions,
    load_exclusions,
    load_static_sources,
    vegetation_only,
)


def _rows(df: pd.DataFrame, status: str) -> list[list]:
    out = []
    for r in df.itertuples():
        ts = pd.Timestamp(r.acq_dt)
        frp = getattr(r, "frp", float("nan"))
        out.append([
            round(float(r.latitude), 5),
            round(float(r.longitude), 5),
            None if pd.isna(ts) else ts.strftime("%Y-%m-%d"),
            str(getattr(r, "satellite", "")),
            None if pd.isna(frp) else round(float(frp), 1),
            status,
        ])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=str(DATA_DIR / "live" / "viirs.csv"))
    ap.add_argument("--date", help="initial date (YYYY-MM-DD); default: all dates")
    ap.add_argument("--out", default=str(DATA_DIR / "results" / "detections_map.html"))
    ap.add_argument("--title", default="FindFire detections")
    a = ap.parse_args()

    raw = pd.read_csv(a.csv)
    if "acq_dt" not in raw.columns:
        raise SystemExit(f"{a.csv}: no acq_dt column")
    raw["acq_dt"] = pd.to_datetime(raw["acq_dt"], utc=True, errors="coerce")

    typed = vegetation_only(raw)
    zones = load_exclusions(include_static=True)
    kept = apply_exclusions(typed, zones)
    removed_mask = typed.drop(index=kept.index)
    removed_type = raw.drop(index=typed.index)

    points = _rows(kept, "kept") + _rows(removed_mask, "mask") + _rows(removed_type, "type")
    dates = sorted({p[2] for p in points if p[2]}, reverse=True)
    if a.date and a.date not in dates:
        raise SystemExit(f"{a.date} has no detections; available: {', '.join(dates)}")
    initial = a.date or ""

    mask = load_static_sources()
    mask_rows = [
        [round(float(r.latitude), 5), round(float(r.longitude), 5), float(r.radius_km),
         str(r.name), int(r.days_seen)]
        for r in mask.itertuples()
    ]

    data = dict(
        title=a.title,
        bbox=list(STUDY_BBOX),
        dates=dates,
        initial=initial,
        points=points,
        mask=mask_rows,
        counts=dict(raw=len(raw), kept=len(kept), mask=len(removed_mask), type=len(removed_type)),
    )

    html = (TEMPLATE.replace("__TITLE__", a.title)
            .replace("__DATA__", json.dumps(data, allow_nan=False)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"raw={len(raw)} kept={len(kept)} mask={len(removed_mask)} type={len(removed_type)} "
          f"dates={len(dates)} -> {out.resolve()}")


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font:13px sans-serif}#map{position:absolute;inset:0}
.panel{position:absolute;z-index:1000;background:#fffffff2;border:1px solid #999;border-radius:6px;padding:8px 10px}
#info{top:10px;left:10px;max-width:360px;line-height:1.5}#info b{font-size:14px}
#controls{top:10px;right:10px;min-width:190px}#controls label{display:block;white-space:nowrap}
#legend{bottom:14px;left:10px}.sw{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;border:1px solid #333;vertical-align:-1px}
.muted{color:#555}select{font:inherit;padding:2px 4px}
</style></head><body><div id="map"></div>
<div class="panel" id="info"><b>__TITLE__</b><br>
<span class="muted">Saved detections, after <code>type</code> + exclusion filters.</span><br><br>
Date <select id="date"></select><br>
<span id="summary"></span><br><br>
<span class="muted">Green: kept. Red: removed by a curated/static source. Orange: removed by FIRMS <code>type</code>.
Red rings: learned static sources (1.5 km).</span></div>
<div class="panel" id="controls"><b>Layers</b>
<label><input type="checkbox" id="c_kept" checked> Kept detections</label>
<label><input type="checkbox" id="c_mask" checked> Removed by source mask</label>
<label><input type="checkbox" id="c_type" checked> Removed by type</label>
<label><input type="checkbox" id="c_static"> Static source rings</label></div>
<div class="panel" id="legend">
<span class="sw" style="background:#2a9d3f"></span>kept
&nbsp;<span class="sw" style="background:#e63946"></span>mask
&nbsp;<span class="sw" style="background:#f4a261"></span>type</div>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas:true}).fitBounds([[D.bbox[1],D.bbox[0]],[D.bbox[3],D.bbox[2]]]);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:18, attribution:'Esri, Maxar, Earthstar Geographics'}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19, attribution:'Tiles &copy; Esri'}).addTo(map);
const G = {kept:L.layerGroup().addTo(map), mask:L.layerGroup().addTo(map),
           type:L.layerGroup().addTo(map), static:L.layerGroup()};
const COL = {kept:'#2a9d3f', mask:'#e63946', type:'#f4a261'};
const NAME = {kept:'kept', mask:'removed by source mask', type:'removed by type'};
const dateSel = document.getElementById('date');
D.dates.forEach(d => { const o = document.createElement('option'); o.value = d; o.textContent = d; dateSel.appendChild(o); });
dateSel.insertAdjacentHTML('afterbegin', '<option value="">all dates</option>');
dateSel.value = D.initial;
function popup(p){
  return `<b>${NAME[p[5]]}</b><br>${p[3]}<br>${p[2]} UTC<br>FRP ${p[4] == null ? '-' : p[4]} MW<br>${p[0].toFixed(4)}, ${p[1].toFixed(4)}`;
}
function drawStatic(){
  G.static.clearLayers();
  for (const m of D.mask){
    L.circle([m[0],m[1]], {radius:m[2]*1000, color:'#e63946', weight:1, dashArray:'4,4', fillOpacity:.10})
      .bindTooltip(`${m[3]} - seen on ${m[4]} distinct days`).addTo(G.static);
  }
}
function draw(){
  const day = dateSel.value;
  for (const k in G) if (k !== 'static') G[k].clearLayers();
  const n = {kept:0, mask:0, type:0};
  for (const p of D.points){
    if (day && p[2] !== day) continue;
    n[p[5]]++;
    L.circleMarker([p[0],p[1]], {radius:p[5] === 'kept' ? 4 : 3, color:'#111', weight:.35,
      fillColor:COL[p[5]], fillOpacity:p[5] === 'kept' ? .9 : .75})
      .bindPopup(popup(p)).addTo(G[p[5]]);
  }
  const total = n.kept + n.mask + n.type;
  document.getElementById('summary').innerHTML =
    `Showing <b>${total}</b> detections: <b style="color:#2a9d3f">${n.kept}</b> kept, ` +
    `<b style="color:#e63946">${n.mask}</b> mask, <b style="color:#d9822b">${n.type}</b> type`;
}
function applyToggles(){
  for (const k of ['kept','mask','type','static']){
    if (document.getElementById('c_'+k).checked) G[k].addTo(map);
    else map.removeLayer(G[k]);
  }
}
['kept','mask','type','static'].forEach(k => document.getElementById('c_'+k).onchange = applyToggles);
dateSel.onchange = draw;
drawStatic();
draw();
applyToggles();
</script></body></html>"""


if __name__ == "__main__":
    main()
