"""Check the land-cover labels of the zones against what you SEE on satellite imagery.

    python scripts/validate_landcover.py                         # 20 zones from data/live/state.json
    python scripts/validate_landcover.py --n 15 --seed 3
    python scripts/validate_landcover.py --state data/live/state.json --tiles D:/worldcover
    python scripts/validate_landcover.py --csv-in data/results/landcover_checks.csv   # score a finished check

Step 1: this script writes data/results/landcover_validation.html. Open it in a browser (it needs internet for the
        Esri imagery tiles).
Step 2: for each zone, look at the imagery and pick what you see. By default the prediction is hidden until you have
        answered (blind check, so the label cannot bias you). Keys: 1-8 answer, left/right arrows move.
Step 3: press "Export CSV". Save it as data/results/landcover_checks.csv and run this script with --csv-in to print
        the agreement table for the report.

Sample: every zone that is mixed, built-up, bare or other is ALWAYS included (those are the risky ones), then random
zones of the remaining tiers up to --n. Zones with no land cover (null) cannot be checked and are skipped.

Tiers (the same rule the dashboard should use):
    confident  majority class, share >= 0.7, crop or forest
    likely     majority class otherwise (grass, scrub, or a share between 0.5 and 0.7)
    mixed      no class covers more than half
    review     the dominant class is built-up, bare or other: look for industrial heat sources or a footprint over a town
    unknown    land_cover is null
"""
import argparse
import json
import random
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape

from findfire.config import DATA_DIR
from findfire.landcover.worldcover import annotate_zones

OBSERVED = ["crop", "forest", "scrub", "grass", "built-up", "bare", "other", "mixed", "unsure"]
RISKY = {"mixed", "review"}


def tier(lc) -> str:
    if lc is None:
        return "unknown"
    if lc["label"] in ("built-up", "bare", "other"):
        return "review"
    if not lc["majority"]:
        return "mixed"
    if lc["dominant_share"] >= 0.7 and lc["label"] in ("crop", "forest"):
        return "confident"
    return "likely"


def sample(zones, n, seed):
    """All risky zones, then random others up to n. Returns the chosen zones, in zone_id order."""
    ok = [z for z in zones if z.get("land_cover")]
    forced = [z for z in ok if tier(z["land_cover"]) in RISKY]
    rest = [z for z in ok if tier(z["land_cover"]) not in RISKY]
    random.Random(seed).shuffle(rest)
    chosen = forced + rest[:max(0, n - len(forced))]
    return sorted(chosen, key=lambda z: z["zone_id"])


def matches(predicted, majority, observed) -> bool:
    """Observed 'mixed' counts as correct when the prediction was flagged mixed (majority false)."""
    if observed == "mixed":
        return not majority
    return observed == predicted


def score(csv_path):
    d = pd.read_csv(csv_path)
    d = d[d["observed"].notna() & (d["observed"] != "unsure")].copy()
    if d.empty:
        raise SystemExit("no answered zones in the CSV")
    d["match"] = [matches(p, bool(m), o) for p, m, o in zip(d["predicted"], d["majority"], d["observed"])]
    print(f"{len(d)} zones checked, agreement {d['match'].mean():.0%} ({int(d['match'].sum())}/{len(d)})\n")
    print("by tier")
    print(d.groupby("tier")["match"].agg(zones="count", agree="sum", rate="mean").round(2).to_string())
    print("\nby predicted label")
    print(d.groupby("predicted")["match"].agg(zones="count", agree="sum", rate="mean").round(2).to_string())
    wrong = d[~d["match"]]
    if len(wrong):
        print("\nwrong zones (predicted -> seen)")
        for r in wrong.itertuples():
            print(f"  zone {r.zone_id}: {r.predicted} ({r.dominant_share:.2f}) -> {r.observed}")
    print("\nReport this next to ESA's global 76.7 %: it is your local figure. With few zones it is rough, "
          "so quote the count as well as the percentage.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default=str(DATA_DIR / "live" / "state.json"))
    ap.add_argument("--out", default=str(DATA_DIR / "results" / "landcover_validation.html"))
    ap.add_argument("--n", type=int, default=20, help="zones to check (risky zones are always included)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tiles"); ap.add_argument("--no-remote", action="store_true")
    ap.add_argument("--csv-in", help="score a finished check instead of building the page")
    a = ap.parse_args()

    if a.csv_in:
        return score(a.csv_in)

    state = json.loads(Path(a.state).read_text())
    zones = [dict(f["properties"], geometry=shape(f["geometry"])) for f in state["zones"]]
    if not zones:
        raise SystemExit("no zones in the state file")
    annotate_zones(zones, a.tiles, remote=not a.no_remote)
    missing = sum(1 for z in zones if not z.get("land_cover"))
    chosen = sample(zones, a.n, a.seed)
    if not chosen:
        raise SystemExit("no zone has land cover: nothing to check")

    items = []
    for z in chosen:
        lc = z["land_cover"]
        items.append(dict(zone_id=int(z["zone_id"]), area_ha=round(float(z["area_ha"]), 1), status=z.get("status", ""),
                          predicted=lc["label"], dominant_share=lc["dominant_share"], majority=bool(lc["majority"]),
                          shares=lc["shares"], tier=tier(lc), geometry=mapping(z["geometry"])))
    tiers = pd.Series([i["tier"] for i in items]).value_counts().to_dict()
    data = dict(items=items, options=OBSERVED)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, allow_nan=False))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{len(items)} of {len(zones)} zones sampled (tiers: {tiers}); {missing} without land cover skipped")
    if len(items) < a.n:
        print(f"note: only {len(items)} zones available, fewer than --n {a.n}")
    print(f"open {out.resolve()}")


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Land-cover check</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<style>
:root{--bg:#fff;--fg:#1d1d1b;--mute:#5d5d58;--line:#c9c9c2;--panel:#fffffff0;--ok:#1f7a3f;--bad:#b3261e;--sel:#e8efe9}
@media (prefers-color-scheme:dark){:root{--bg:#171715;--fg:#eceae4;--mute:#a4a29a;--line:#47473f;--panel:#1f1f1cf0;--ok:#5cc383;--bad:#ff8a80;--sel:#2a3a2f}}
html,body{margin:0;height:100%;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
#map{position:absolute;inset:0}
.panel{position:absolute;z-index:1000;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px 12px}
#ask{top:10px;left:10px;width:300px;max-height:calc(100% - 20px);overflow:auto}
#sum{top:10px;right:10px;width:250px}
h1{font-size:15px;margin:0 0 4px}
.mute{color:var(--mute)}
#opts button{display:block;width:100%;text-align:left;margin:3px 0;padding:6px 8px;font:inherit;color:inherit;background:transparent;
  border:1px solid var(--line);border-radius:4px;cursor:pointer}
#opts button:hover,#opts button:focus-visible{border-color:var(--fg);outline:none}
#opts button.on{background:var(--sel);border-color:var(--ok)}
.nav{display:flex;gap:6px;margin-top:8px}.nav button,#exp{font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:4px;padding:5px 10px;cursor:pointer}
.nav button:hover,#exp:hover{border-color:var(--fg)}
table{border-collapse:collapse;width:100%}td,th{padding:2px 4px;text-align:right}td:first-child,th:first-child{text-align:left}
.ok{color:var(--ok)}.bad{color:var(--bad)}
@media (max-width:700px){#sum{display:none}#ask{width:auto;right:10px}}
</style></head><body><div id="map"></div>
<div class="panel" id="ask">
  <h1 id="title"></h1><div class="mute" id="meta"></div>
  <div id="reveal" style="margin:6px 0"></div>
  <div class="mute" style="margin:6px 0 2px">What do you see inside the outline?</div>
  <div id="opts"></div>
  <div class="nav"><button id="prev">Previous</button><button id="next">Next</button></div>
  <label class="mute" style="display:block;margin-top:8px"><input type="checkbox" id="blind" checked> Hide the prediction until I answer</label>
  <div class="mute" style="margin-top:6px">Keys: 1-9 answer, arrows move. Satellite imagery is often older than the fire, so judge what the land was.</div>
</div>
<div class="panel" id="sum"></div>
<script>
const D = __DATA__;
const items = D.items, opts = D.options, ans = {};
const map = L.map('map');
const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19, attribution:'Esri, Maxar, Earthstar Geographics'}).addTo(map);
const street = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19, attribution:'Tiles &copy; Esri'});
L.control.layers({'Satellite':sat,'Street map':street}, null, {position:'bottomright'}).addTo(map);
let cur = 0, layer = null;
const $ = id => document.getElementById(id);
const match = (it, o) => o === 'mixed' ? !it.majority : o === it.predicted;
const shareText = s => Object.entries(s).sort((a,b)=>b[1]-a[1]).map(([k,v]) => k+' '+Math.round(v*100)+'%').join(', ');

function show(i){
  cur = Math.max(0, Math.min(items.length-1, i)); const it = items[cur];
  if(layer) map.removeLayer(layer);
  layer = L.geoJSON(it.geometry, {style:{color:'#ffd400', weight:3, fill:false}}).addTo(map);
  map.fitBounds(layer.getBounds().pad(1.2));
  $('title').textContent = 'Zone '+it.zone_id+'  ('+(cur+1)+' of '+items.length+')';
  $('meta').textContent = it.area_ha+' ha, '+it.status;
  const revealed = !$('blind').checked || ans[it.zone_id];
  $('reveal').innerHTML = revealed
    ? 'Prediction: <b>'+it.predicted+'</b> ('+Math.round(it.dominant_share*100)+'%, '+it.tier+')<br><span class="mute">'+shareText(it.shares)+'</span>'
    : '<span class="mute">Prediction hidden.</span>';
  $('opts').innerHTML = '';
  opts.forEach((o,k) => { const b = document.createElement('button');
    b.textContent = (k+1)+'  '+o; if(ans[it.zone_id] === o) b.classList.add('on');
    b.onclick = () => answer(o); $('opts').appendChild(b); });
  summary();
}
function answer(o){ ans[items[cur].zone_id] = o; show(cur); if(cur < items.length-1) setTimeout(() => show(cur+1), 250); }

function summary(){
  const done = items.filter(it => ans[it.zone_id] && ans[it.zone_id] !== 'unsure');
  const agree = done.filter(it => match(it, ans[it.zone_id]));
  const by = {};
  done.forEach(it => { const t = by[it.tier] = by[it.tier] || {n:0, a:0}; t.n++; if(match(it, ans[it.zone_id])) t.a++; });
  let h = '<b>Progress</b><br>'+Object.keys(ans).length+' of '+items.length+' answered<br>';
  if(done.length){
    h += '<br><b>Agreement</b> '+Math.round(100*agree.length/done.length)+'% ('+agree.length+'/'+done.length+')<table><tr><th>tier</th><th>zones</th><th>agree</th></tr>'
      + Object.entries(by).map(([t,v]) => '<tr><td>'+t+'</td><td>'+v.n+'</td><td class="'+(v.a===v.n?'ok':'bad')+'">'+v.a+'</td></tr>').join('')+'</table>';
  }
  h += '<br><button id="exp">Export CSV</button>';
  $('sum').innerHTML = h; $('exp').onclick = exportCsv;
}
function exportCsv(){
  const head = ['zone_id','area_ha','tier','predicted','dominant_share','majority','observed'];
  const rows = items.map(it => [it.zone_id, it.area_ha, it.tier, it.predicted, it.dominant_share, it.majority, ans[it.zone_id] || ''].join(','));
  const url = URL.createObjectURL(new Blob([head.join(',')+'\n'+rows.join('\n')+'\n'], {type:'text/csv'}));
  const a = document.createElement('a'); a.href = url; a.download = 'landcover_checks.csv'; a.click(); URL.revokeObjectURL(url);
}
$('prev').onclick = () => show(cur-1); $('next').onclick = () => show(cur+1); $('blind').onchange = () => show(cur);
document.addEventListener('keydown', e => {
  if(e.key === 'ArrowRight') show(cur+1); else if(e.key === 'ArrowLeft') show(cur-1);
  else if(/^[1-9]$/.test(e.key) && opts[+e.key-1]) answer(opts[+e.key-1]);
});
show(0);
</script></body></html>
"""


if __name__ == "__main__":
    main()
