#!/usr/bin/env python3
"""Denver bike safety spatial analysis.

Cross-checks 3,521 bicycle-involved crashes (2013-2026) against the city's
completed bike facility network: how many crashes happened on vs off
infrastructure, severity differences, hit-and-run clustering, unprotected
high-crash corridors, and time trends.

Method: equirectangular projection centered on Denver, point-to-segment
distance in meters (pure numpy, no geopandas). 25 m snap threshold.

Outputs: key numbers to stdout, full stats to notes/findings.json.
"""
import csv, json, math, re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

DATA = "/home/hatch/workspace/denver-bike-safety/data"
OUT = "/home/hatch/workspace/denver-bike-safety/notes/findings.json"

LAT0, LON0 = 39.7392, -104.9903
KX = 111320 * math.cos(math.radians(LAT0))   # meters per degree lon at Denver
KY = 110540                                   # meters per degree lat
SNAP_M = 25.0
PROTECTED = "Protected Bike Lane"

# ---------------------------------------------------------------- load crashes
crashes = []
with open(f"{DATA}/denver_bicycle_crashes.csv") as f:
    for r in csv.DictReader(f):
        try:
            lon = float(r["geo_lon"]) if r["geo_lon"] else None
            lat = float(r["geo_lat"]) if r["geo_lat"] else None
        except ValueError:
            lon = lat = None
        crashes.append({
            "lon": lon, "lat": lat,
            "offense": r["top_traffic_accident_offense"].strip(),
            "date": (r["first_occurrence_date"] or "")[:10],
            "addr": (r["incident_address"] or "").strip(),
            "fatalities": int(r["FATALITIES"] or 0),
            "ser_inj": int(r["SERIOUSLY_INJURED"] or 0),
            "fat_mode": r["FATALITY_MODE_1"].strip(),
            "sbi_mode": r["SERIOUSLY_INJURED_MODE_1"].strip(),
            "nbhd": r["neighborhood_id"].strip(),
        })
geo = [c for c in crashes if c["lon"] is not None and c["lat"] is not None]
print(f"crashes: {len(crashes)} total, {len(geo)} with coords, "
      f"{len(crashes)-len(geo)} missing coords (excluded from spatial)")

# ------------------------------------------------------- load completed facilities
with open(f"{DATA}/denver_bike_facilities.geojson") as f:
    gj = json.load(f)

def explode(feat):
    """Yield (coords-list, props) per LineString."""
    g = feat["geometry"]; p = feat["properties"]
    if p.get("STATUS", "").strip() != "Completed":
        return
    t = (p.get("FACILITY_TYPE_EXISTING") or "").strip()
    yr_raw = (p.get("INSTALL_YEAR_MOST_RECENT") or "").strip()
    m = re.search(r"(19|20)\d{2}", yr_raw)
    yr = int(m.group(0)) if m else (2000 if yr_raw.lower().startswith("pre") else None)
    if g["type"] == "LineString":
        yield g["coordinates"], t, yr, (p.get("STREET_NAME") or "").strip()
    elif g["type"] == "MultiLineString":
        for ls in g["coordinates"]:
            yield ls, t, yr, (p.get("STREET_NAME") or "").strip()

segs = []  # (ax,ay,bx,by,type,year,street) in meters
for feat in gj["features"]:
    for coords, t, yr, st in explode(feat):
        pts = [((x - LON0) * KX, (y - LAT0) * KY) for x, y in coords]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            if ax == bx and ay == by:
                continue
            segs.append((ax, ay, bx, by, t, yr, st))
print(f"completed facility segments: {len(segs)}")
print("completed by type:", dict(Counter(s[4] for s in segs)))

S = np.array([(a[0], a[1], a[2], a[3]) for a in segs])
TYPES = [a[4] for a in segs]
YEARS = np.array([a[5] if a[5] else 9999 for a in segs])  # unknown -> always present
ax, ay, bx, by = S[:, 0], S[:, 1], S[:, 2], S[:, 3]
dx, dy = bx - ax, by - ay
seg_len2 = dx * dx + dy * dy

def nearest_facility(px, py, crash_year=None):
    """Return (dist_m, type) of nearest completed segment; time-aware if year given."""
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / seg_len2, 0, 1)
    cx, cy = ax + t * dx, ay + t * dy
    d = np.hypot(px - cx, py - cy)
    if crash_year is not None:
        d = np.where(YEARS <= crash_year, d, np.inf)
    i = int(np.argmin(d))
    return float(d[i]), TYPES[i]

# ------------------------------------------------------------------ tag crashes
for c in geo:
    px, py = (c["lon"] - LON0) * KX, (c["lat"] - LAT0) * KY
    d, t = nearest_facility(px, py)
    c["dist_m"] = d
    c["near_type"] = t if d <= SNAP_M else None
    c["on_infra"] = d <= SNAP_M
    yr = int(c["date"][:4]) if c["date"] else None
    d2, t2 = nearest_facility(px, py, crash_year=yr)
    c["on_infra_timeaware"] = d2 <= SNAP_M
    c["near_type_ta"] = t2 if d2 <= SNAP_M else None

on = [c for c in geo if c["on_infra"]]
off = [c for c in geo if not c["on_infra"]]
on_prot = [c for c in on if c["near_type"] == PROTECTED]
print(f"\non infra (<=25m): {len(on)} ({100*len(on)/len(geo):.1f}%)  "
      f"off infra: {len(off)} ({100*len(off)/len(geo):.1f}%)")
print(f"on protected lanes: {len(on_prot)} ({100*len(on_prot)/len(geo):.1f}% of all)")
print("crashes by facility type:", dict(Counter(c["near_type"] for c in on)))
on_ta = sum(1 for c in geo if c["on_infra_timeaware"])
print(f"time-aware on-infra (facility existed at crash date): {on_ta} "
      f"({100*on_ta/len(geo):.1f}%)")

# -------------------------------------------------------------------- severity
def sev(sub):
    kf = sum(c["fatalities"] for c in sub if c["fat_mode"] == "BICYCLE")
    si = sum(c["ser_inj"] for c in sub if c["sbi_mode"] == "BICYCLE")
    n = len(sub)
    return {"n": n, "bicyclist_killed": kf, "bicyclist_seriously_injured": si,
            "ksi": kf + si, "ksi_rate": (kf + si) / n if n else 0}

s_on, s_off = sev(on), sev(off)
print(f"\nseverity on infra:  {s_on['ksi']} KSI / {s_on['n']} = {100*s_on['ksi_rate']:.2f}% "
      f"({s_on['bicyclist_killed']} killed, {s_on['bicyclist_seriously_injured']} seriously injured)")
print(f"severity off infra: {s_off['ksi']} KSI / {s_off['n']} = {100*s_off['ksi_rate']:.2f}% "
      f"({s_off['bicyclist_killed']} killed, {s_off['bicyclist_seriously_injured']} seriously injured)")
s_prot = sev(on_prot)
print(f"severity on protected: {s_prot['ksi']} KSI / {s_prot['n']} = "
      f"{100*s_prot['ksi_rate']:.2f}%")

# ----------------------------------------------------------------- hit and run
hrs = [c for c in geo if "HIT" in c["offense"]]
print(f"\nhit-and-run with coords: {len(hrs)} "
      f"({100*len([c for c in crashes if 'HIT' in c['offense']])/len(crashes):.1f}% of all crashes)")

CELL = 500  # meters
def cell_key(c):
    px, py = (c["lon"] - LON0) * KX, (c["lat"] - LAT0) * KY
    return (int(px // CELL), int(py // CELL), round((int(px // CELL) + 0.5) * CELL / KX + LON0, 4),
            round((int(py // CELL) + 0.5) * CELL / KY + LAT0, 4))

def street_of(addr):
    s = addr.split("/")[0].strip()
    s = re.sub(r"^\d+\s+BLOCK\s+", "", s, flags=re.I)
    s = re.sub(r"^\d+\s+", "", s)
    return s or "(unknown)"

hr_cells = defaultdict(list)
for c in hrs:
    hr_cells[cell_key(c)[:2]].append(c)
top_hr = sorted(hr_cells.items(), key=lambda kv: -len(kv[1]))[:10]
print("top hit-and-run 500m cells (count, center lon/lat, top street):")
hr_top = []
for (cx, cy), lst in top_hr:
    cl = cell_key(lst[0])
    st = Counter(street_of(c["addr"]) for c in lst).most_common(1)[0][0]
    hr_top.append({"cell": [cx, cy], "count": len(lst),
                   "center": [cl[2], cl[3]], "top_street": st})
    print(f"  {len(lst):3d}  ({cl[2]}, {cl[3]})  {st}")

# --------------------------------------- top corridors WITHOUT protected infra
CELL2 = 250
cells = defaultdict(list)
for c in geo:
    px, py = (c["lon"] - LON0) * KX, (c["lat"] - LAT0) * KY
    cells[(int(px // CELL2), int(py // CELL2))].append(c)

# protected segment bboxes (expanded) for quick cell test
pb = [(min(a[0], a[2]) - 30, min(a[1], a[3]) - 30,
       max(a[0], a[2]) + 30, max(a[1], a[3]) + 30)
      for a in segs if a[4] == PROTECTED]

def cell_has_protected(cx, cy):
    x0, y0 = cx * CELL2, cy * CELL2
    x1, y1 = x0 + CELL2, y0 + CELL2
    return any(px0 < x1 and px1 > x0 and py0 < y1 and py1 > y0 for px0, py0, px1, py1 in pb)

cands = []
for (cx, cy), lst in cells.items():
    if cell_has_protected(cx, cy):
        continue
    px = (cx + 0.5) * CELL2 / KX + LON0
    py = (cy + 0.5) * CELL2 / KY + LAT0
    st = Counter(street_of(c["addr"]) for c in lst).most_common(1)[0][0]
    ksi = sum(1 for c in lst if (c["fat_mode"] == "BICYCLE" and c["fatalities"]) or
              (c["sbi_mode"] == "BICYCLE" and c["ser_inj"]))
    cands.append({"cell": [cx, cy], "count": len(lst), "ksi": ksi,
                  "center": [round(px, 4), round(py, 4)], "top_street": st,
                  "on_infra_pct": round(100 * sum(1 for c in lst if c["on_infra"]) / len(lst), 1)})
cands.sort(key=lambda d: -d["count"])
print("\ntop 10 high-crash 250m cells with NO protected infra nearby:")
for d in cands[:10]:
    print(f"  {d['count']:3d} crashes ({d['ksi']} KSI), {d['on_infra_pct']}% on-infra  "
          f"({d['center'][0]}, {d['center'][1]})  {d['top_street']}")

# ----------------------------------------------------------------- time trend
annual = Counter(c["date"][:4] for c in crashes if c["date"])
print("\nannual bike crash counts:")
for y in sorted(annual):
    print(f"  {y}: {annual[y]}")
monthly = Counter(c["date"][:7] for c in crashes if c["date"] >= "2025-01")
print("monthly 2025-2026:")
for m in sorted(monthly):
    print(f"  {m}: {monthly[m]}")

# ------------------------------------------------------------------ findings
findings = {
    "crashes_total": len(crashes),
    "crashes_with_coords": len(geo),
    "crashes_missing_coords": len(crashes) - len(geo),
    "on_infra_n": len(on), "on_infra_pct": round(100 * len(on) / len(geo), 1),
    "off_infra_n": len(off), "off_infra_pct": round(100 * len(off) / len(geo), 1),
    "on_protected_n": len(on_prot),
    "on_protected_pct_of_all": round(100 * len(on_prot) / len(geo), 1),
    "crashes_by_facility_type": dict(Counter(c["near_type"] for c in on)),
    "on_infra_timeaware_n": on_ta,
    "on_infra_timeaware_pct": round(100 * on_ta / len(geo), 1),
    "severity_on_infra": {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in s_on.items()},
    "severity_off_infra": {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in s_off.items()},
    "severity_on_protected": {k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in s_prot.items()},
    "hit_run_total": sum(1 for c in crashes if "HIT" in c["offense"]),
    "hit_run_pct": round(100 * sum(1 for c in crashes if "HIT" in c["offense"]) / len(crashes), 1),
    "hit_run_top_cells": hr_top,
    "top_unprotected_corridors": cands[:10],
    "annual_counts": dict(sorted(annual.items())),
    "monthly_2025_2026": dict(sorted(monthly.items())),
    "caveats": [
        "71 crashes (2%) lack coordinates and are excluded from all spatial stats.",
        "25m snap threshold: intersection crashes may snap to a crossing facility; GPS/geocode error unquantified.",
        "Facility network is the 2026 snapshot; pre-2013-crash facilities mostly 'Pre 2010'. Time-aware variant included.",
        "21 fatal crashes have FATALITY_MODE_1='UNDER INVESTIGATION'; bicyclist death count (21) may rise.",
        "Hit-and-run and severity rely on officer coding; underreporting of minor bike crashes is well documented.",
        "Trail crashes (237 completed trail segments) include off-street paths where 'on infrastructure' is expected.",
    ],
}
with open(OUT, "w") as f:
    json.dump(findings, f, indent=2)
print(f"\nwrote {OUT}")
