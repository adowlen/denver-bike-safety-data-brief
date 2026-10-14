# Where Denver Cyclists Get Hit

A data brief on bicycle crash geography in Denver, Colorado: 3,521 police-reported bike crashes (2013-2026) mapped against the city's bike network, its Vision Zero High Injury Network, and street speed data.

**Headline:** 4 out of 5 bike crashes happen where no bike infrastructure exists - and the deadliest corridors are streets the city already flagged as dangerous but never protected for cyclists.

Read the full brief: [brief/denver-bike-safety-brief.md](brief/denver-bike-safety-brief.md)

## Contents

- `brief/` - the narrative brief with findings, charts, methods, and caveats
- `charts/` - 6 charts (PNG)
- `data/` - aggregated statistics (JSON). Point-level crash coordinates are withheld; use Denver's open data portal to reproduce.
- `code/` - analysis scripts (`analyze.py`, `analyze_v2.py`) and chart generation (`make_charts.py`)

## Data sources

All from Denver's Open Data Catalog (ArcGIS Hub):

- Traffic Accidents (Denver Police Department) - 3,521 bicycle-involved records, 2013-2026
- Bike Facilities - 2,025 segments with facility type and status
- High Injury Network - 496 Vision Zero segments, Tier 1/2
- Street Centerlines - 30,706 segments with posted speed limits

## Reproduce

1. Download the four datasets above from https://denvergov.org/opendata
2. Run `python code/analyze.py` then `python code/analyze_v2.py`
3. Run `python code/make_charts.py` for the charts

Requires Python 3 with geopandas, shapely, matplotlib.

## Methods and data

The public datasets listed under Data sources are analyzed with [code/analyze.py](code/analyze.py) and [code/analyze_v2.py](code/analyze_v2.py); charts are generated with [code/make_charts.py](code/make_charts.py). Aggregate outputs are in the JSON files in [data/](data/). Point-level crash coordinates are withheld, as noted under Contents.

## Part of Machine Readable

This brief is part of [Machine Readable](https://adowlen.github.io/machine-readable/), the catalog of all Machine Readable briefs.
