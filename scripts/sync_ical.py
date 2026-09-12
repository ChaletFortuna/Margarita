#!/usr/bin/env python3
"""
Fetch booked dates from Airbnb / VRBO iCal feeds and write availability.json.
Run automatically by the GitHub Action (.github/workflows/sync-calendar.yml).

Villa Margarita, Beaulieu-sur-Mer. To change a feed, edit ICAL_URLS below:
 - Airbnb: Calendar -> Availability -> Connect to another website -> copy link
 - VRBO:   Calendar -> Import & export -> Export calendar -> copy link
"""
import json, re, urllib.request
from datetime import datetime, date

ICAL_URLS = [
    "https://www.airbnb.fr/calendar/ical/20203939.ics?s=79e51972bdef7f08ffec2439c37ae9a5",
    "http://www.vrbo.com/icalendar/f4a5239154ee4b79bbca12cd8d0e6b4b.ics",
]

def parse_ical(text):
    """Return list of (start, end) date ranges for busy events. DTEND is exclusive (check-out day)."""
    ranges = []
    for ev in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        if re.search(r"SUMMARY:.*(available)\s*$", ev, re.I | re.M) and not re.search(r"not available|unavailable|reserved|blocked", ev, re.I):
            continue  # skip "Available" events some feeds include
        m1 = re.search(r"DTSTART[^:]*:(\d{8})", ev)
        m2 = re.search(r"DTEND[^:]*:(\d{8})", ev)
        if m1 and m2:
            fmt = lambda s: f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
            ranges.append((fmt(m1.group(1)), fmt(m2.group(1))))
    return ranges

def merge(ranges):
    ranges = sorted(set(ranges))
    out = []
    for s, e in ranges:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out

def main():
    all_ranges = []
    for url in ICAL_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                all_ranges += parse_ical(r.read().decode("utf-8", "replace"))
        except Exception as ex:
            print(f"WARNING: could not fetch {url}: {ex}")
    today = date.today().isoformat()
    booked = [{"start": s, "end": e} for s, e in merge(all_ranges) if e >= today]
    data = {"updated": datetime.utcnow().isoformat() + "Z", "booked": booked}
    with open("availability.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote availability.json with {len(booked)} booked range(s).")

if __name__ == "__main__":
    main()
