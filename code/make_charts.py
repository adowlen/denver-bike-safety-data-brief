"""Charts for the Denver bike safety brief. Reads findings JSONs, writes PNGs to charts/."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTS = os.path.join(BASE, "charts")
os.makedirs(CHARTS, exist_ok=True)

with open(os.path.join(BASE, "notes", "findings.json")) as f:
    F1 = json.load(f)
with open(os.path.join(BASE, "notes", "findings_v2.json")) as f:
    F2 = json.load(f)

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
})
ACCENT = "#b91c1c"   # red for danger numbers
DARK = "#1f2937"
MID = "#6b7280"
BLUE = "#1d4ed8"
TEAL = "#0f766e"
LIGHT = "#d1d5db"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, name), bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# (a) crashes on vs off infrastructure
fig, ax = plt.subplots(figsize=(7, 4.2))
cats = ["On protected\nbike lane", "On other bike\ninfrastructure", "Off the bike\nnetwork entirely"]
vals = [211, 689 - 211, 2761]
colors = [TEAL, BLUE, ACCENT]
bars = ax.bar(cats, vals, color=colors, width=0.6)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 40,
            f"{v:,}", ha="center", va="bottom", fontsize=12, fontweight="bold")
ax.set_ylabel("Bicycle crashes, 2013-2026")
ax.set_title("4 out of 5 bike crashes happen off the bike network", fontsize=13, fontweight="bold", pad=12)
ax.set_ylim(0, 3100)
save(fig, "on_vs_off_infra.png")

# (b) KSI rate by speed limit
fig, ax = plt.subplots(figsize=(7, 4.2))
speeds = ["25 mph", "30 mph", "35 mph", "40+ mph"]
rates = [7.6, 9.43, 12.07, 8.77]
ns = [1815, 901, 381, 171]
colors = [MID, "#f59e0b", "#f97316", ACCENT]
bars = ax.bar(speeds, rates, color=colors, width=0.6)
for b, r, n in zip(bars, rates, ns):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.25,
            f"{r:.1f}%\n(n={n:,})", ha="center", va="bottom", fontsize=10)
ax.set_ylabel("Killed or seriously injured, % of crashes")
ax.set_title("Faster streets kill more cyclists", fontsize=13, fontweight="bold", pad=12)
ax.set_ylim(0, 15)
save(fig, "ksi_by_speed.png")

# (c) top 8 corridors: crashes with protected-lane coverage
top8 = F2["hin_tier1_gaps"][:8]
streets = [t["street"].title() for t in top8]
crashes = [t["crashes"] for t in top8]
prot = [t["on_protected"] for t in top8]
fig, ax = plt.subplots(figsize=(8, 4.8))
y = range(len(streets))
bars = ax.barh(list(y), crashes, color=LIGHT, height=0.55)
for i, (c, p) in enumerate(zip(crashes, prot)):
    label = f"{c} crashes, {p} near protected" if p else f"{c} crashes, none protected"
    ax.text(c + 2, i, label, va="center", fontsize=10,
            color=ACCENT if p == 0 else DARK, fontweight="bold" if p == 0 else "normal")
ax.set_yticks(list(y))
ax.set_yticklabels(streets)
ax.invert_yaxis()
ax.set_xlabel("Bicycle crashes on Tier 1 High Injury Network segments")
ax.set_title("The city's most dangerous streets have almost no protected bike lanes",
             fontsize=13, fontweight="bold", pad=12)
ax.grid(axis="x", alpha=0.3)
save(fig, "corridor_protection_gap.png")

# (d) annual crash trend
fig, ax = plt.subplots(figsize=(8, 4.2))
years = sorted(int(k) for k in F1["annual_counts"])
counts = [F1["annual_counts"][str(y)] for y in years]
ax.plot(years, counts, marker="o", color=DARK, linewidth=2.5, markersize=5)
ax.fill_between(years, counts, alpha=0.08, color=DARK)
ax.axvspan(2019.5, 2021.5, color=MID, alpha=0.12)
ax.text(2020.5, max(counts) * 0.92, "COVID dip", ha="center", fontsize=10, color=MID)
ax.annotate("2025: rebound\nto 217", xy=(2025, 217), xytext=(2022.2, 260),
            arrowprops=dict(arrowstyle="->", color=ACCENT), fontsize=10, color=ACCENT,
            fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Bicycle crashes")
ax.set_title("Bike crashes are climbing back after the COVID dip", fontsize=13, fontweight="bold", pad=12)
ax.set_xticks(years)
ax.set_xticklabels(years, rotation=45, ha="right", fontsize=9)
save(fig, "annual_trend.png")

# (e) hit-and-run hotspots by street (aggregated from top cells)
hr = {}
for cell in F1["hit_run_top_cells"]:
    st = cell["top_street"].replace(" ST", "").replace(" AVE", "").title()
    hr[st] = hr.get(st, 0) + cell["count"]
top_hr = sorted(hr.items(), key=lambda x: -x[1])[:7]
fig, ax = plt.subplots(figsize=(7, 4.2))
labels = [k for k, _ in top_hr]
vals = [v for _, v in top_hr]
bars = ax.bar(labels, vals, color=ACCENT, width=0.6)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.4,
            str(v), ha="center", va="bottom", fontsize=11, fontweight="bold")
ax.set_ylabel("Hit-and-run bike crashes")
ax.set_title("Hit-and-runs cluster downtown: 1 in 4 bike crashes is a fleeing driver",
             fontsize=13, fontweight="bold", pad=12)
ax.set_xticklabels(labels, rotation=20, ha="right")
save(fig, "hit_run_hotspots.png")

# (f) HIN Tier 1: share of bike crashes near any bike infrastructure, top 10 by crashes
top10 = F2["hin_tier1_gaps"][:10]
streets10 = [t["street"].title() for t in top10]
onbike = [t["on_bike_pct"] for t in top10]
fig, ax = plt.subplots(figsize=(8, 5))
y = range(len(streets10))
colors10 = [TEAL if p >= 25 else ("#f59e0b" if p > 0 else ACCENT) for p in onbike]
bars = ax.barh(list(y), onbike, color=colors10, height=0.55)
for i, p in enumerate(onbike):
    ax.text(p + 1, i, f"{p:.0f}%", va="center", fontsize=10)
ax.set_yticks(list(y))
ax.set_yticklabels(streets10)
ax.invert_yaxis()
ax.set_xlabel("% of bike crashes within 25m of any bike infrastructure")
ax.set_title("Even on the High Injury Network, most bike crashes are off infrastructure",
             fontsize=13, fontweight="bold", pad=12)
ax.set_xlim(0, 115)
ax.grid(axis="x", alpha=0.3)
save(fig, "hin_infra_coverage.png")

print("done")
