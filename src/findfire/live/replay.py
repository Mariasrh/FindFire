"""Standalone HTML replay: time slider + play, zone footprints, trail of earlier outlines, hotspots, MTG alerts,
and the exclusion mask as toggleable overlays. One file, opens in any browser (Leaflet from a CDN, Esri tiles)."""
from __future__ import annotations

import json

import pandas as pd
from shapely.geometry import mapping

from findfire.config import STUDY_BBOX

def _num(v, nd=1):
    v = float(v)
    return 0.0 if v != v else round(v, nd)


iso = lambda t: None if pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_data(result, exclusions=None, title="FindFire replay") -> dict:
    steps = []
    for s in result["snaps"]:
        z = [dict(type="Feature", geometry=mapping(r["geometry"]), properties={
            k: (iso(v) if k.endswith("detected") else _num(v, 2) if isinstance(v, float) else v)
            for k, v in r.items() if k != "geometry"}) for r in s["zones"]]
        h = [[round(r.latitude, 5), round(r.longitude, 5), iso(r.acq_dt), _num(r.frp), int(r.zone_id), r.satellite]
             for r in s["hotspots"].itertuples()]
        a = [dict(id=int(r.alert_id), lat=r.latitude, lon=r.longitude, status=r.status, first=iso(r.first_detected),
                  scans=int(r.n_scans), lead=None if pd.isna(r.lead_time_min) else round(r.lead_time_min))
             for r in s["alerts"].itertuples()] if len(s["alerts"]) else []
        steps.append(dict(t=iso(s["time"]), zones=z, hot=h, alerts=a))
    mask = [] if exclusions is None else exclusions[["name", "latitude", "longitude", "radius_km"]].to_dict("records")
    return dict(title=title, bbox=STUDY_BBOX, steps=steps, mask=mask,
                merges=[[iso(t), int(a), int(b)] for t, a, b in result["merges"]])


def page(data: dict | None, events=None, title="FindFire replay") -> str:
    """The HTML page. data=None -> empty page that loads events through the local server (scripts/serve_replay.py)."""
    return (TEMPLATE.replace("__TITLE__", title).replace("__DATA__", json.dumps(data, allow_nan=False))
            .replace("__EVENTS__", json.dumps(events or [])))


def render_replay(result, path, exclusions=None, title="FindFire replay", events=None):
    open(path, "w", encoding="utf-8").write(page(to_data(result, exclusions, title), events, title))


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font:13px sans-serif} #map{position:absolute;inset:0}
.panel{position:absolute;z-index:1000;background:#fffffff2;border:1px solid #999;border-radius:6px;padding:8px 10px}
#ctl{left:50%;transform:translateX(-50%);bottom:12px;width:min(720px,92vw)} #ctl input[type=range]{width:100%}
#side{top:10px;right:10px;max-height:60vh;overflow:auto;min-width:230px} #side table{border-collapse:collapse;width:100%}
#side td,#side th{padding:2px 5px;text-align:right} #side th{border-bottom:1px solid #aaa} #side tr:hover{background:#eee;cursor:pointer}
#tog{top:10px;left:50px} #tog label{display:block;white-space:nowrap}
.sw{display:inline-block;width:10px;height:10px;margin-right:4px;border:1px solid #333}
</style></head><body><div id="map"></div>
<div class="panel" id="tog"><b>__TITLE__</b>
<label><input type="checkbox" id="c_zones" checked> Zone footprints</label>
<label><input type="checkbox" id="c_trail" checked> Earlier outlines (growth)</label>
<label><input type="checkbox" id="c_hot" checked> Hotspots</label>
<label><input type="checkbox" id="c_alerts" checked> MTG early alerts</label>
<label><input type="checkbox" id="c_mask"> Exclusion mask</label>
<div style="margin-top:4px"><span class="sw" style="background:#e63946"></span>new <span class="sw" style="background:#f4a261"></span>active <span class="sw" style="background:#6c757d"></span>inactive</div></div>
<div class="panel" id="evt" style="top:10px;left:50%;transform:translateX(-50%);max-width:46vw">
Event <select id="preset"><option value="">custom</option></select>
from <input type="date" id="d0"> to <input type="date" id="d1"><br>
groups <select id="mn"><option value="1">loose</option><option value="2">medium</option><option value="3">strict</option></select>
footprint <select id="fp"><option value="alpha">alpha shape</option><option value="close">closing</option><option value="boxes">pixels</option></select>
edge <input id="ef" type="number" step="0.05" min="0" max="1" value="0.5" style="width:52px">
<button id="load">Load &amp; replay</button> <span id="status" style="color:#555"></span></div>
<div class="panel" id="side"></div>
<div class="panel" id="ctl"><div id="lbl" style="font-weight:bold;margin-bottom:4px"></div>
<input type="range" id="sl" min="0" value="0">
<button id="prev">&#9664;</button> <button id="play">&#9654; Play</button> <button id="next">&#9654;</button>
speed <select id="spd"><option value="1200">slow</option><option value="600" selected>normal</option><option value="250">fast</option></select>
<span id="note" style="color:#555"> Estimates only: satellite pixels, 'inactive' means no detections, not necessarily out.</span></div>
<script>
let D = __DATA__ || {title:'',bbox:[-2,34,8.5,37.5],steps:[],mask:[],merges:[]};
const EVENTS = __EVENTS__, SERVER = location.protocol.startsWith('http');
const map = L.map('map'); const b = D.bbox;
const street = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles &copy; Esri'}).addTo(map);
const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles &copy; Esri'});
L.control.layers({'Street map':street,'Satellite':sat}).addTo(map);
map.fitBounds([[b[1],b[0]],[b[3],b[2]]]);
const G = {zones:L.layerGroup().addTo(map), trail:L.layerGroup().addTo(map), hot:L.layerGroup().addTo(map),
           alerts:L.layerGroup().addTo(map), mask:L.layerGroup()};
const COL = {new:'#e63946', active:'#f4a261', inactive:'#6c757d'}, ACOL = {confirmed:'#2a9d8f', pending:'#e9c46a', not_confirmed:'#8d99ae'};
D.mask.forEach(m => L.circle([m.latitude,m.longitude],{radius:m.radius_km*1000,color:'#444',dashArray:'5 5',weight:1,fillOpacity:.15})
  .bindTooltip('Excluded: '+m.name).addTo(G.mask));
const local = s => new Date(Date.parse(s)+3600e3).toISOString().slice(5,16).replace('T',' ');
let cur = 0, timer = null;
const sl = document.getElementById('sl'); sl.max = Math.max(D.steps.length-1,0);
const $ = id => document.getElementById(id);
function draw(i){
  cur = i; sl.value = i; Object.values(G).forEach(g => g.clearLayers());
  D.mask.forEach(m => L.circle([m.latitude,m.longitude],{radius:m.radius_km*1000,color:'#444',dashArray:'5 5',weight:1,fillOpacity:.15}).bindTooltip('Excluded: '+m.name).addTo(G.mask));
  const S = D.steps[i]; if(!S) return;
  document.getElementById('lbl').textContent = local(S.t)+' (UTC+1)  |  step '+(i+1)+' of '+D.steps.length;
  for(let k=Math.max(0,i-12); k<i; k++){
    const a = 0.15 + 0.6*(k-Math.max(0,i-12))/Math.max(1,i-Math.max(0,i-12));
    D.steps[k].zones.forEach(z => L.geoJSON(z,{style:{color:'#222',weight:1,fill:false,opacity:a}}).addTo(G.trail));
  }
  S.zones.forEach(z => { const p = z.properties;
    L.geoJSON(z,{style:{color:'black',weight:2,fillColor:COL[p.status],fillOpacity:.45}})
     .bindPopup('<b>Zone #'+p.zone_id+'</b> ('+p.status+')<br>'+p.area_ha.toLocaleString()+' ha (estimate), '+p.perimeter_km+' km perimeter<br>'
       +p.n_hotspots+' hotspots, FRP '+Math.round(p.frp_total_mw)+' MW<br>first '+local(p.first_detected)+', last '+local(p.last_detected)+' (UTC+1)')
     .addTo(G.zones); });
  for(let k=0;k<=i;k++) D.steps[k].hot.forEach(h => L.circleMarker([h[0],h[1]],{radius:k==i?4:2.5,weight:.5,
      color:h[4]>=0?'#c1121f':'#898781',fillOpacity:k==i?.9:.35,opacity:k==i?1:.5}).bindTooltip(local(h[2])+' '+h[5]+' FRP '+h[3]).addTo(G.hot));
  S.alerts.forEach(a => L.circleMarker([a.lat,a.lon],{radius:9,weight:2,color:ACOL[a.status],fillOpacity:.3})
     .bindPopup('<b>MTG alert #'+a.id+'</b> ('+a.status+')<br>first '+local(a.first)+', '+a.scans+' scans'+(a.lead==null?'':'<br>MTG was '+a.lead+' min before VIIRS')).addTo(G.alerts));
  const prev = {}; if(i>0) D.steps[i-1].zones.forEach(z => prev[z.properties.zone_id] = z.properties.area_ha);
  let rows = S.zones.slice().sort((x,y)=>y.properties.area_ha-x.properties.area_ha).map(z => { const p=z.properties, d = prev[p.zone_id]==null?'new':(p.area_ha-prev[p.zone_id]>0.5?'+'+Math.round(p.area_ha-prev[p.zone_id]):'');
    return '<tr data-z="'+p.zone_id+'"><td>#'+p.zone_id+'</td><td>'+p.status+'</td><td>'+Math.round(p.area_ha)+' ha</td><td>'+d+'</td></tr>'; }).join('');
  const mg = D.merges.filter(m => m[0]==S.t).map(m => 'zone '+m[1]+' merged into '+m[2]).join('; ');
  document.getElementById('side').innerHTML = '<table><tr><th>zone</th><th>status</th><th>area</th><th>change</th></tr>'+(rows||'<tr><td colspan=4>no zones yet</td></tr>')+'</table>'+(mg?'<div style="margin-top:4px">'+mg+'</div>':'');
  document.querySelectorAll('#side tr[data-z]').forEach(tr => tr.onclick = () => { const z = S.zones.find(q => q.properties.zone_id==tr.dataset.z); map.fitBounds(L.geoJSON(z).getBounds().pad(2)); });
  applyToggles();
}
function applyToggles(){ for(const k of ['zones','trail','hot','alerts','mask']){ const on = document.getElementById('c_'+k).checked; if(on) G[k].addTo(map); else map.removeLayer(G[k]); } }
['zones','trail','hot','alerts','mask'].forEach(k => document.getElementById('c_'+k).onchange = applyToggles);
sl.oninput = () => draw(+sl.value);
document.getElementById('prev').onclick = () => draw(Math.max(0,cur-1));
document.getElementById('next').onclick = () => draw(Math.min(D.steps.length-1,cur+1));
function stop(){ clearInterval(timer); timer=null; document.getElementById('play').innerHTML='&#9654; Play'; }
document.getElementById('play').onclick = () => { if(timer){stop();return;} document.getElementById('play').innerHTML='&#10074;&#10074; Pause';
  if(cur>=D.steps.length-1) draw(0);
  timer = setInterval(() => { if(cur>=D.steps.length-1){stop();return;} draw(cur+1); }, +document.getElementById('spd').value); };
document.getElementById('spd').onchange = () => { if(timer){ stop(); document.getElementById('play').click(); } };
function setData(nd){ stop(); D = nd; sl.max = Math.max(D.steps.length-1,0);
  const pts = []; D.steps.forEach(s => { s.hot.forEach(h => pts.push([h[0],h[1]])); });
  if(pts.length) map.fitBounds(pts, {padding:[60,60], maxZoom:11});
  draw(0); }
EVENTS.forEach((e,i) => { const o = document.createElement('option'); o.value = i; o.textContent = e.name+' ('+e.start+' to '+e.end+')'; $('preset').appendChild(o); });
$('preset').onchange = () => { const e = EVENTS[+$('preset').value]; if(e){ $('d0').value = e.start; $('d1').value = e.end; } };
$('load').onclick = async () => {
  if(!SERVER){ $('status').textContent = 'Open this page through scripts/serve_replay.py to load other dates.'; return; }
  if(!$('d0').value || !$('d1').value){ $('status').textContent = 'Pick a start and an end date.'; return; }
  $('load').disabled = true; $('status').textContent = 'Loading... (first load of a new period downloads from FIRMS)';
  try {
    const q = new URLSearchParams({start:$('d0').value, end:$('d1').value, min_neighbors:$('mn').value, footprint:$('fp').value, edge:$('ef').value});
    const r = await fetch('/api/replay?'+q); const j = await r.json();
    if(j.error){ $('status').textContent = j.error; }
    else { setData(j); $('status').textContent = j.steps.length+' steps. '+(j.notes||[]).join(' '); }
  } catch(err){ $('status').textContent = 'Failed: '+err; }
  $('load').disabled = false; };
if(!SERVER && !D.steps.length) $('evt').style.display = 'none';
draw(D.steps.length ? D.steps.length-1 : 0);
</script></body></html>
"""
