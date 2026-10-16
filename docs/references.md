# References

## Data sources

### NASA FIRMS
- Source used: VIIRS_NOAA20_NRT (375 m resolution)
- Role: precise hotspot location and area
- Access: area API with Algeria bounding box, MAP_KEY in .env

### EUMETSAT Data Store
- Collection used: EO:EUM:DAT:0682, Active Fire Monitoring (netCDF), MTG
- Role: fast and frequent detection that triggers the alert
- Access: eumdac library, key and secret in .env
- Other candidates: EO:EUM:DAT:0801 (CAP format),
  EO:EUM:DAT:0417 (Sentinel-3 FRP)
- TODO (Day 2): confirm resolution, update frequency, latency and
  product format from the collection page