"""Static HTML map (open in a browser). Zones, hotspots, MTG alerts, and an honest 'as of' banner."""
from __future__ import annotations

import folium
import pandas as pd
from shapely.geometry import mapping

from findfire.config import STUDY_BBOX

LOCAL = pd.Timedelta(hours=1)      # Algeria is UTC+1 all year
STATUS = {"new": "#e63946", "active": "#f4a261", "inactive": "#6c757d"}
ALERT = {"confirmed": "#2a9d8f", "pending": "#e9c46a", "not_confirmed": "#8d99ae"}


def _t(x): return "-" if pd.isna(x) else f"{pd.Timestamp(x) + LOCAL:%d %b %H:%M}"


def render(zones, hotspots, alerts, banner: str, path, refresh_s: int = 120):
    w, s, e, n = STUDY_BBOX
    m = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                 attr="Tiles &copy; Esri", name="Street map", overlay=False).add_to(m)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri", name="Satellite", overlay=False, show=False).add_to(m)
    m.fit_bounds([[s, w], [n, e]])
    fz, fh, fa = (folium.FeatureGroup(name=x) for x in ("VIIRS zones", "VIIRS hotspots", "MTG early alerts"))
    for z in zones:
        folium.GeoJson(mapping(z["geometry"]), tooltip=f"Zone #{z['zone_id']}: {z['area_ha']:,.0f} ha",
                       popup=folium.Popup(f"<b>Zone #{z['zone_id']}</b> ({z['status']})<br>{z['area_ha']:,.0f} ha (estimate), "
                                          f"{z['perimeter_km']:.1f} km perimeter<br>{z['n_hotspots']} hotspots, FRP {z['frp_total_mw']:.0f} MW"
                                          f"<br>first {_t(z['first_detected'])}, last {_t(z['last_detected'])} (UTC+1)", max_width=300),
                       style_function=lambda _, c=STATUS[z["status"]]: dict(color="black", weight=2, fillColor=c, fillOpacity=0.45)).add_to(fz)
    for r in hotspots.itertuples():
        folium.CircleMarker([r.latitude, r.longitude], radius=3, weight=0.5, fill=True, fill_opacity=0.8,
                            color="#c1121f" if r.zone_id >= 0 else "#898781",
                            tooltip=f"{_t(r.acq_dt)} (UTC+1) {r.satellite} FRP {r.frp:.1f}").add_to(fh)
    for r in alerts.itertuples():
        lead = "" if pd.isna(r.lead_time_min) else f"<br>MTG was {r.lead_time_min:.0f} min before VIIRS"
        folium.CircleMarker([r.latitude, r.longitude], radius=9, weight=2, color=ALERT[r.status], fill=True, fill_opacity=0.35,
                            popup=folium.Popup(f"<b>MTG alert #{r.alert_id}</b> ({r.status})<br>first {_t(r.first_detected)}, "
                                               f"{r.n_scans} scans (UTC+1){lead}", max_width=280)).add_to(fa)
    for g in (fz, fh, fa):
        g.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().header.add_child(folium.Element(f'<meta http-equiv="refresh" content="{refresh_s}">'))
    m.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;bottom:8px;left:50%;transform:translateX(-50%);z-index:9999;background:white;"
        f"padding:4px 10px;border:1px solid #999;border-radius:4px;font:12px sans-serif'>{banner}</div>"))
    m.save(str(path))
