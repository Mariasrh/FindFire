"""Run this FIRST, once, with your EUMETSAT keys in .env. It checks the real FIR file against the assumptions in ingestion/mtg.py.

    python scripts/inspect_mtg.py
Prints: the collection, the latest granules, the datasets satpy can read, the fire_result class names, and how many
fire pixels fall in the study box. If the class names are not what fire_classes() expects, fix it there (one function).
"""
from datetime import datetime, timedelta, timezone

from satpy import Scene

from findfire.config import MTG_FIR_COLLECTION, STUDY_BBOX
from findfire.ingestion import mtg

store = mtg.datastore()
col = store.get_collection(MTG_FIR_COLLECTION)
print("collection:", col, "|", col.title)

end = datetime.now(timezone.utc).replace(tzinfo=None)
products = mtg.list_products(end - timedelta(hours=3), end, store)
print(f"{len(products)} granules in the last 3 h; newest sensing times:", [str(p.sensing_start) for p in products[-3:]])
if not products:
    raise SystemExit("no granules: check the collection id, your key, or whether the product is still pre-operational")

files = mtg.download(products[-1])
print("files:", [f.name for f in files])
scn = Scene(filenames=[str(f) for f in files], reader="fci_l2_nc")
print("datasets:", sorted(scn.available_dataset_names()))
scn.load(["fire_result"])
fr = scn["fire_result"]
print("shape:", fr.shape, "| classes:", dict(zip(fr.attrs.get("flag_values", []), fr.attrs.get("flag_meanings", []))))
print("start_time:", fr.attrs.get("start_time"), "| end_time:", fr.attrs.get("end_time"))
df = mtg.fire_pixels(fr, bbox=STUDY_BBOX)
print(f"fire pixels in study box: {len(df)}\n", df.head(10).to_string())
