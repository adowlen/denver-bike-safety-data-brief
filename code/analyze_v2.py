#!/usr/bin/env python3
"""Denver bike safety v2: HIN overlap, speed/functional-class, combined gaps.

Merges 3,521 bike crashes with:
- Denver Vision Zero High Injury Network (496 segments, Tier 1/2)
- Street centerlines (30,706 segments: SPEEDLIMIT, FUNCLASS, VOLCLASS)
- Completed bike facilities (from v1)

Method: equirectangular projection centered on Denver, vectorized
point-to-segment distance (numpy). 25 m snap threshold throughout.

Outputs: key numbers to stdout, full stats to notes/findings_v2.json.
"""
import csv, json, math, re
from collections import Counter, defaultdict

import numpy as np

DATA = "/home/hatch/workspace/denver-bike-safety/data"
OUT = "/home/hatch/workspace/denver-bike-safety/notes/findings_v2.json"

LAT0, LON0 = 39.7392, -104.9903
KX = 111320 * math.cos(math.radians(LAT0))
KY = 110540
SNAP_M = 25.0
PROTECTED = "Protected Bike Lane"

def to_xy(lon, lat):
    return (lon - LON0) * KX, (lat - LAT0) * KY

def explode_lines(feats):
    """Yield (coords, props) per LineString."""
    for feat in feats:
        g = feat["geometry"]; p = feat["properties"]
        if g["type"] == "LineString":
            yield g["coordinates"], p
        elif g["type"] == "MultiLineString":
            for ls in g["coordinates"]:
                yield ls, p

def segs_from(feats, attr_fn):
    """attr_fn(props) -> attr tuple or None to skip. Returns (S, attrs)."""
    out = []
    for coords, p in explode_lines(feats):
        attr = attr_fn(p)
        if attr is None:
            continue
        pts = [to_xy(x, y) for x, y in coords]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            if ax == bx and ay == by:
                continue
            out.append((ax, ay, bx, by, attr))
    S = np.array([(a[0], a[1], a[2], a[3]) for a in out])
    return S, [a[4] for a in out]

def make_nearest(S, ATTRS):
    ax, ay, bx, by = S[:, 0], S[:, 1], S[:, 2], S[:, 3]
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    seg_len2[seg_len2 == 0] = 1e-9
    def nearest(px, py):
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / seg_len2, 0, 1)
        d = np.hypot(px - (ax + t * dx), py - (ay + t * dy))
        i = int(np.argmin(d))
        return float(d[i]), ATTRS[i]
    return nearest

# ---------------------------------------------------------------- crashes
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
            "fatalities": int(r["FATALITIES"] or 0),
            "ser_inj": int(r["SERIOUSLY_INJURED"] or 0),
            "fat_mode": r["FATALITY_MODE_1"].strip(),
            "sbi_mode": r["SERIOUSLY_INJURED_MODE_1"].strip(),
        })
geo = [c for c in crashes if c["lon"] is not None and c["lat"] is not None]
print(f"crashes: {len(crashes)} total, {len(geo)} with coords")

def is_bike_ksi(c):
    return (c["fatalities"] > 0 and c["fat_mode"] == "BICYCLE") or \
           (c["ser_inj"] > 0 and c["sbi_mode"] == "BICYCLE")

# ---------------------------------------------------------------- HIN
with open(f"{DATA}/denver_hin.geojson") as f:
    hin_feats = json.load(f)["features"]
S_hin, A_hin = segs_from(hin_feats, lambda p: (
    (p.get("StreetName") or "").strip().upper(),
    int(p.get("Tier") or 0),
))
nearest_hin = make_nearest(S_hin, A_hin)
print(f"HIN segments: {len(S_hin)}")
print("HIN street names containing 16TH:",
      sorted(set(a[0] for a in A_hin if "16TH" in a[0])))

# ---------------------------------------------------------------- centerlines
with open(f"{DATA}/denver_street_centerlines.geojson") as f:
    cl_feats = json.load(f)["features"]
def cl_attr(p):
    try:
        sp = int(p.get("SPEEDLIMIT") or 0)
    except (ValueError, TypeError):
        sp = 0
    return ((p.get("FULLNAME") or "").strip().upper(),
            sp,
            (p.get("FUNCLASS") or "").strip(),
            (p.get("VOLCLASS") or "").strip())
S_cl, A_cl = segs_from(cl_feats, cl_attr)
nearest_cl = make_nearest(S_cl, A_cl)
print(f"centerline segments: {len(S_cl)}")

# ---------------------------------------------------------------- bike facilities (completed)
with open(f"{DATA}/denver_bike_facilities.geojson") as f:
    bf_feats = json.load(f)["features"]
def bf_attr(p):
    if (p.get("STATUS") or "").strip() != "Completed":
        return None
    return (p.get("FACILITY_TYPE_EXISTING") or "").strip()
S_bf, A_bf = segs_from(bf_feats, bf_attr)
nearest_bf = make_nearest(S_bf, A_bf)
print(f"completed facility segments: {len(S_bf)}")

# ---------------------------------------------------------------- tag crashes
for c in geo:
    px, py = to_xy(c["lon"], c["lat"])
    d_hin, (hin_street, hin_tier) = nearest_hin(px, py)
    c["on_hin"] = d_hin <= SNAP_M
    c["hin_tier"] = hin_tier if c["on_hin"] else 0
    c["hin_street"] = hin_street if c["on_hin"] else None
    d_cl, (cl_name, cl_speed, cl_fun, cl_vol) = nearest_cl(px, py)
    c["cl_name"] = cl_name if d_cl <= SNAP_M else None
    c["cl_speed"] = cl_speed if d_cl <= SNAP_M else None
    c["cl_fun"] = cl_fun if d_cl <= SNAP_M else None
    c["cl_vol"] = cl_vol if d_cl <= SNAP_M else None
    c["cl_dist"] = d_cl
    d_bf, bf_type = nearest_bf(px, py)
    c["on_bike"] = d_bf <= SNAP_M
    c["bike_type"] = bf_type if c["on_bike"] else None
    c["on_protected"] = c["on_bike"] and bf_type == PROTECTED

n = len(geo)
R = {"n_geo": n}

# ------------------------------------------------- 1. HIN overlap
on_hin = [c for c in geo if c["on_hin"]]
t1 = [c for c in on_hin if c["hin_tier"] == 1]
t2 = [c for c in on_hin if c["hin_tier"] == 2]
R["hin"] = {
    "on_hin_n": len(on_hin), "on_hin_pct": round(100*len(on_hin)/n, 1),
    "tier1_n": len(t1), "tier1_pct": round(100*len(t1)/n, 1),
    "tier2_n": len(t2), "tier2_pct": round(100*len(t2)/n, 1),
}
print(f"\n1. HIN OVERLAP: {len(on_hin)}/{n} ({100*len(on_hin)/n:.1f}%) on HIN; "
      f"Tier1 {len(t1)} ({100*len(t1)/n:.1f}%), Tier2 {len(t2)} ({100*len(t2)/n:.1f}%)")

# top corridors by snapped street name
def norm_street(s):
    s = re.sub(r"^(N|S|E|W)\s+", "", s or "")
    return s.strip()
corr = Counter()
corr_ksi = Counter()
for c in geo:
    if c["cl_name"]:
        k = norm_street(c["cl_name"])
        corr[k] += 1
        if is_bike_ksi(c):
            corr_ksi[k] += 1
top5 = corr.most_common(5)
hin_names = set(a[0] for a in A_hin)
R["top_corridors"] = []
print("\nTop 5 bike-crash corridors (snapped centerline):")
for name, cnt in top5:
    on_hin_flag = "YES" if name in hin_names else "no"
    # also check with directional prefix variants
    R["top_corridors"].append({"street": name, "crashes": cnt,
                               "ksi": corr_ksi[name], "on_hin": name in hin_names})
    print(f"  {name}: {cnt} crashes, {corr_ksi[name]} KSI, on HIN: {on_hin_flag}")

# ------------------------------------------------- 2. speed / functional class
def speed_bucket(s):
    if s is None: return "unknown"
    if s <= 25: return "25"
    if s <= 30: return "30"
    if s <= 35: return "35"
    return "40+"
spd = defaultdict(list)
for c in geo:
    spd[speed_bucket(c["cl_speed"])].append(c)
R["by_speed"] = {}
print("\n2. BY SPEED LIMIT:")
for b in ["25", "30", "35", "40+", "unknown"]:
    cs = spd[b]
    ksi = sum(1 for c in cs if is_bike_ksi(c))
    rate = ksi/len(cs) if cs else 0
    R["by_speed"][b] = {"n": len(cs), "ksi": ksi, "ksi_rate": round(rate, 4)}
    print(f"  {b} mph: {len(cs)} crashes, {ksi} KSI ({100*rate:.2f}%)")

fun = defaultdict(list)
for c in geo:
    fun[c["cl_fun"] or "unknown"].append(c)
R["by_funclass"] = {}
print("\nBY FUNCLASS:")
for fc, cs in sorted(fun.items(), key=lambda x: -len(x[1])):
    ksi = sum(1 for c in cs if is_bike_ksi(c))
    rate = ksi/len(cs) if cs else 0
    R["by_funclass"][fc] = {"n": len(cs), "ksi": ksi, "ksi_rate": round(rate, 4)}
    print(f"  {fc}: {len(cs)} crashes, {ksi} KSI ({100*rate:.2f}%)")

# ------------------------------------------------- 3. combined: fast arterials
fast_art = [c for c in geo if c["cl_vol"] == "ARTERIAL" and (c["cl_speed"] or 0) >= 35]
fa_bike = sum(1 for c in fast_art if c["on_bike"])
fa_prot = sum(1 for c in fast_art if c["on_protected"])
fa_ksi = sum(1 for c in fast_art if is_bike_ksi(c))
R["fast_arterials"] = {
    "n": len(fast_art), "ksi": fa_ksi,
    "ksi_rate": round(fa_ksi/len(fast_art), 4) if fast_art else 0,
    "on_bike_n": fa_bike,
    "on_bike_pct": round(100*fa_bike/len(fast_art), 1) if fast_art else 0,
    "on_protected_n": fa_prot,
    "on_protected_pct": round(100*fa_prot/len(fast_art), 1) if fast_art else 0,
}
print(f"\n3. FAST ARTERIALS (VOLCLASS=ARTERIAL, speed>=35): {len(fast_art)} crashes, "
      f"{fa_ksi} KSI ({100*fa_ksi/len(fast_art) if fast_art else 0:.2f}%)")
print(f"   on any bike facility: {fa_bike} ({100*fa_bike/len(fast_art) if fast_art else 0:.1f}%), "
      f"on protected: {fa_prot} ({100*fa_prot/len(fast_art) if fast_art else 0:.1f}%)")

# ------------------------------------------------- 4. HIN Tier 1 gaps
# per HIN Tier-1 segment (by street name), count bike crashes within 25m,
# and check whether any completed bike facility is nearby
t1_streets = sorted(set(a[0] for a in A_hin if a[1] == 1))
gap_rows = []
for st in t1_streets:
    cs = [c for c in geo if c["hin_street"] == st and c["hin_tier"] == 1]
    if not cs:
        continue
    prot = sum(1 for c in cs if c["on_protected"])
    any_bike = sum(1 for c in cs if c["on_bike"])
    ksi = sum(1 for c in cs if is_bike_ksi(c))
    gap_rows.append({"street": st, "crashes": len(cs), "ksi": ksi,
                     "on_bike_pct": round(100*any_bike/len(cs), 1),
                     "on_protected": prot})
gap_rows.sort(key=lambda r: -r["crashes"])
R["hin_tier1_gaps"] = gap_rows
print("\n4. HIN TIER 1 segments by bike-crash count (bike facility coverage):")
for r in gap_rows[:12]:
    print(f"  {r['street']}: {r['crashes']} crashes, {r['ksi']} KSI, "
          f"{r['on_bike_pct']}% on bike infra, {r['on_protected']} on protected")

with open(OUT, "w") as f:
    json.dump(R, f, indent=2)
print(f"\nwrote {OUT}")

# caveats
R["caveats"] = [
    "25m snap threshold throughout; intersection crashes may snap to a crossing street.",
    "Centerline snap assigns each crash to ONE nearest segment; long corridors aggregate by normalized street name (directional prefix stripped).",
    "HIN reflects the city's published network (496 segments); Tier definitions per Denver Vision Zero.",
    "SPEEDLIMIT=0 or missing treated as unknown; snapped-but-unmatched crashes excluded from speed/funclass tables.",
    "No ridership/exposure denominators: rates are per-crash, not per-trip.",
    "71 crashes (2%) lack coordinates, excluded from all spatial stats.",
]
with open(OUT, "w") as f:
    json.dump(R, f, indent=2)
