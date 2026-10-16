import eumdac

from findfire.config import EUMETSAT_KEY, EUMETSAT_SECRET

token = eumdac.AccessToken((EUMETSAT_KEY, EUMETSAT_SECRET))
datastore = eumdac.DataStore(token)

for collection in datastore.collections:
    text = f"{collection.title} {collection.abstract}".lower()
    if "fire" in text:
        print(collection, "|", collection.title)