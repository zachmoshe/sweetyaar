#!/usr/bin/env python3
"""Build the battery-under-stress report from readings.csv.

Prints the report to battery-under-stress.pdf next to this file with headless
Chrome:

    python3 docs/findings/battery-under-stress/build_report.py

Standard library only. readings.csv is the toy's telemetry exported from its
log uploads: one row per 5-minute reading, with cumulative playback hours.
"""

import csv
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN, LAST = (4100, 3500), (3400, 3200)
ALIGN_MV = 4200
RUNS = {  # csv run id -> label, colour
    "2": ("SD card playback", "#E8762D"),
    "3": ("Bluetooth playback", "#2F6FDB"),
}


def load():
    runs = {}
    for r in csv.DictReader(open(HERE / "readings.csv", newline="")):
        if r["run"] in RUNS and r["playing"] == "1":
            runs.setdefault(r["run"], []).append((float(r["playH"]), int(r["mV"]), r["time"]))
    return {k: sorted(v) for k, v in runs.items()}


def fit(points, band):
    hi, lo = band
    q = [(h, v) for h, v, _ in points if lo <= v <= hi]
    mh = sum(h for h, _ in q) / len(q)
    mv = sum(v for _, v in q) / len(q)
    slope = sum((h - mh) * (v - mv) for h, v in q) / sum((h - mh) ** 2 for h, _ in q)
    h0, h1 = q[0][0], q[-1][0]
    return {"rate": -slope, "h0": h0, "h1": h1, "v0": mv + slope * (h0 - mh), "v1": mv + slope * (h1 - mh)}


def at(points, h):
    for (h0, v0, _), (h1, v1, _) in zip(points, points[1:]):
        if h0 <= h <= h1 and h1 > h0:
            return v0 + (v1 - v0) * (h - h0) / (h1 - h0)
    return points[0][1]


def analyse(runs):
    out = {}
    for run, p in runs.items():
        end = p[-1][0]
        start = next(h for h, v, _ in p if v <= ALIGN_MV)
        out[run] = {
            "points": p, "end": end, "start": start, "hours": end - start,
            "main": fit(p, MAIN), "last": fit(p, LAST), "emptyMv": p[-1][1],
            "v90": at(p, end - 1.5), "v30": at(p, end - 0.5),
        }
    warn90 = math.ceil(max(r["v90"] for r in out.values()) / 10) * 10
    warn30 = math.ceil(max(r["v30"] for r in out.values()) / 10) * 10
    for r in out.values():  # how early the shared warnings come in each mode
        p = r["points"]
        r["lead90"] = r["end"] - next(h for h, v, _ in p if v <= warn90)
        r["lead30"] = r["end"] - next(h for h, v, _ in p if v <= warn30)
    return out, warn90, warn30


def axes(w, h, pad, xr, yr, xticks, yticks, xfmt, yfmt):
    l, r, t, b = pad
    sx = lambda x: l + (x - xr[0]) / (xr[1] - xr[0]) * (w - l - r)
    sy = lambda y: t + (yr[1] - y) / (yr[1] - yr[0]) * (h - t - b)
    s = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-size="9" font-family="inherit">']
    for y in yticks:
        s.append(f'<line x1="{l}" x2="{w - r}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" stroke="#e4e4e4"/>')
        s.append(f'<text x="{l - 4}" y="{sy(y) + 3:.1f}" text-anchor="end" fill="#666">{yfmt(y)}</text>')
    for x in xticks:
        s.append(f'<text x="{sx(x):.1f}" y="{h - b + 12}" text-anchor="middle" fill="#666">{xfmt(x)}</text>')
    s.append(f'<line x1="{l}" x2="{w - r}" y1="{h - b}" y2="{h - b}" stroke="#999"/>')
    return s, sx, sy


def path(pts, sx, sy, colour, extra=""):
    d = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts))
    return f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="1.6" stroke-linejoin="round" {extra}/>'


def chart_full(res):
    xmax = math.ceil(max(r["hours"] for r in res.values()) / 5) * 5
    s, sx, sy = axes(360, 175, (34, 10, 8, 20), (0, xmax), (3.0, 4.3), range(0, xmax + 1, 5),
                     [3.0 + i * 0.2 for i in range(7)], lambda x: f"{x} h", lambda y: f"{y:.1f} V")
    for run, r in res.items():
        colour = RUNS[run][1]
        s.append(path([(h - r["start"], v / 1000) for h, v, _ in r["points"] if h >= r["start"]], sx, sy, colour))
        for f in (r["main"], r["last"]):  # fitted rates, drawn just above the readings
            s.append(f'<line x1="{sx(f["h0"] - r["start"]):.1f}" x2="{sx(f["h1"] - r["start"]):.1f}" '
                     f'y1="{sy(f["v0"] / 1000) - 5:.1f}" y2="{sy(f["v1"] / 1000) - 5:.1f}" stroke="{colour}" '
                     f'stroke-width="1.2" stroke-dasharray="4 3"/>')
    s.append("</svg>")
    return "".join(s)


def chart_end(res, warn90, warn30):
    lo = math.floor(min(min(v for h, v, _ in r["points"] if h >= r["end"] - 3) for r in res.values()) / 100) * 100 / 1000
    hi = math.ceil(max(max(v for h, v, _ in r["points"] if h >= r["end"] - 3) for r in res.values()) / 100) * 100 / 1000
    s, sx, sy = axes(360, 175, (40, 18, 8, 20), (-180, 0), (lo, hi), range(-180, 1, 30),
                     [lo + i * 0.1 for i in range(round((hi - lo) / 0.1) + 1)],
                     lambda x: "empty" if x == 0 else f"{x} min", lambda y: f"{y:.1f} V")
    for mv, text in ((warn90, "90 min warning"), (warn30, "30 min warning")):
        s.append(f'<line x1="40" x2="342" y1="{sy(mv / 1000):.1f}" y2="{sy(mv / 1000):.1f}" stroke="#555" stroke-dasharray="4 3"/>')
        s.append(f'<text x="44" y="{sy(mv / 1000) - 3:.1f}" fill="#444">{text}: {mv / 1000:.2f} V</text>')
    for run, r in res.items():
        s.append(path([((h - r["end"]) * 60, v / 1000) for h, v, _ in r["points"] if h >= r["end"] - 3], sx, sy, RUNS[run][1]))
    s.append("</svg>")
    return "".join(s)


def hm(hours):
    return f"{int(hours)} h {round(hours % 1 * 60):02d} min"


def html(res, warn90, warn30):
    sd, bt = res["2"], res["3"]
    rows = "".join(
        f'<tr><td><i style="background:{RUNS[k][1]}"></i>{RUNS[k][0]}</td><td>{r["hours"]:.1f} h</td>'
        f'<td>{r["main"]["rate"]:.0f}</td><td>{r["last"]["rate"]:.0f}</td><td>{2600 / r["hours"]:.0f} mA</td>'
        f'<td>{r["emptyMv"] / 1000:.2f} V</td><td>{r["v90"] / 1000:.2f} V</td><td>{r["v30"] / 1000:.2f} V</td></tr>'
        for k, r in res.items())
    legend = " ".join(f'<span><i style="background:{c}"></i>{n}</span>' for n, c in RUNS.values())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Battery runtime under continuous playback</title>
<style>
  @page {{ size: A4; margin: 10mm 13mm; }}
  body {{ font: 9pt/1.34 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1d1d1f; margin: 0; }}
  h1 {{ font-size: 16pt; margin: 0; font-weight: 600; }}
  .sub {{ color: #666; margin: 2px 0 8px; }}
  h2 {{ font-size: 10.5pt; margin: 7px 0 3px; padding-bottom: 2px; border-bottom: 1px solid #ddd; }}
  p, ul {{ margin: 3px 0; }}
  ul {{ padding-left: 16px; }}
  li {{ margin: 1px 0; }}
  .setup {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 8.6pt; margin-top: 3px; font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: right; padding: 2px 5px; white-space: nowrap; border-bottom: 1px solid #e6e6e6; }}
  th {{ color: #555; font-weight: 600; }}
  th:first-child, td:first-child {{ text-align: left; }}
  i {{ display: inline-block; width: 12px; height: 3px; border-radius: 1px; margin: 0 5px 2px 0; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 4px; }}
  .charts h3 {{ font-size: 9pt; margin: 0; }}
  .charts p {{ color: #666; font-size: 8pt; margin: 0 0 2px; }}
  .legend {{ font-size: 8.4pt; color: #444; margin-top: 4px; }}
  .legend span {{ margin-right: 14px; }}
  .rec {{ background: #f5f6f8; border-left: 3px solid #2F6FDB; padding: 4px 10px; margin-top: 4px; }}
  code {{ font-size: 8.5pt; }}
</style></head><body>
<h1>Battery runtime under continuous playback</h1>
<div class="sub">SweetYaar bench finding · November 2026 · device “Yaaruli Debug”</div>

<h2>Goal</h2>
<p>Measure how long a full charge lasts in the toy's two heaviest modes, playing songs from the SD card and
streaming over Bluetooth, and derive the battery voltages at which to warn 90 and 30 minutes before the toy
runs out.</p>

<h2>Setup</h2>
<div class="setup">
<ul>
  <li>Production SweetYaar PCB v1.0, PlatformIO env <code>sweetyaar</code>.</li>
  <li>Firmware 1.2.0.</li>
  <li>2600 mAh Li-ion cell, charged to full before each run.</li>
  <li>4 Ω speaker connected.</li>
</ul>
<ul>
  <li><b>SD card:</b> songs looped from the card, local volume 100&nbsp;%, lowered to 50&nbsp;% by Bedtime for about a third of the run.</li>
  <li><b>Bluetooth:</b> a laptop streaming over Classic Bluetooth (A2DP), mostly at full volume (it may have been lower for part of the run).</li>
  <li>Voltage is the toy's own telemetry: a rolling mean of ten ADC samples 30 s apart, stored every 5 minutes, measured under load.</li>
</ul>
</div>

<h2>Results</h2>
<p>Bluetooth playback is the hardest mode for the battery. The voltage fell <b>{bt["main"]["rate"] / sd["main"]["rate"]:.1f}×</b>
as fast as with SD card playback over the main part of the discharge, and a full charge lasted
<b>{bt["hours"]:.1f} h</b> instead of <b>{sd["hours"]:.1f} h</b>. Both runs end with a steep drop of about
{min(sd["last"]["rate"], bt["last"]["rate"]):.0f}–{max(sd["last"]["rate"], bt["last"]["rate"]):.0f} mV/h below 3.4 V. Under Bluetooth the toy also stopped
<b>earlier on the voltage scale</b>: it reset (power-on reset, no crash) at {bt["emptyMv"] / 1000:.2f} V, while SD playback ran down to
{sd["emptyMv"] / 1000:.2f} V, most likely because the radio's current peaks pull the supply below the brown-out level
while the averaged reading still looks healthy. The firmware never reported Low in either run: its Low threshold
({3100 / 1000:.2f} V) is below both end points.</p>
<table>
  <thead><tr><th>Mode</th><th>Playback<br>from 4.2 V</th><th>Drop 4.1–3.5 V<br>mV/h</th><th>Drop 3.4–3.2 V<br>mV/h</th>
  <th>Implied mean<br>current*</th><th>Stopped<br>at</th><th>V at<br>−90 min</th><th>V at<br>−30 min</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p style="font-size:8pt;color:#666">Drop rates are least-squares slopes against playback hours. *The rated 2600 mAh divided by the
playback time; a rough figure that assumes the cell delivered its rated capacity. Pauses are excluded from playback time.</p>

<div class="legend">{legend}<span style="color:#666">dashed: fitted drop rate</span></div>
<div class="charts">
  <div><h3>Voltage over playback time</h3><p>Hours of playback since the reading first fell to 4.2 V.</p>{chart_full(res)}</div>
  <div><h3>The last 3 hours</h3><p>Minutes before each run's last reading, with the recommended warnings.</p>{chart_end(res, warn90, warn30)}</div>
</div>

<h2>Recommendations</h2>
<div class="rec">
<ul>
  <li><b>Warn 90 minutes before empty at {warn90 / 1000:.2f} V</b> and <b>30 minutes before at {warn30 / 1000:.2f} V</b>
  (the higher of the two modes, rounded up to 10 mV). Bluetooth sets both; during SD playback they arrive early,
  about {hm(sd["lead90"])} and {hm(sd["lead30"])} before empty, which errs on the safe side.</li>
  <li>The thresholds apply to readings under load. A resting toy reads higher, so the same charge can show Good at rest
  and Medium while playing.</li>
</ul>
</div>
</body></html>
"""


def main():
    res, warn90, warn30 = analyse(load())
    chrome = shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome).exists():
        sys.exit("Chrome not found; it prints the report to PDF")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html(res, warn90, warn30))
        subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={HERE / 'battery-under-stress.pdf'}", page.as_uri()],
                       check=True, capture_output=True)
    print(HERE / "battery-under-stress.pdf")


if __name__ == "__main__":
    main()
