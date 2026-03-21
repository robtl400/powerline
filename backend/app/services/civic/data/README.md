# ZIP Centroid Data

`uszips.csv` is used by `openstates.py` to resolve ZIP codes to lat/lng for the OpenStates geo endpoint.

## Bundled file

The file currently bundled is a minimal sample (~24 US zip codes) sufficient for development and testing.

## Production setup

For production, replace `uszips.csv` with the full simplemaps US ZIP Code Database (free tier, ~33k rows):

1. Go to https://simplemaps.com/data/us-zips
2. Download the free Basic CSV
3. Unzip and replace `uszips.csv` in this directory

Required columns: `zip`, `lat`, `lng` (additional columns are ignored).

The file is loaded at module import time (~3 MB, negligible memory). Unknown ZIP codes return an empty rep list with a `log.warning`.
