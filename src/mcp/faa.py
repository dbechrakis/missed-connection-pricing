"""FAA ATCSCC advisories: every ground stop and ground delay program at the five hubs, as the FAA wrote them.

Season 2, WP6 (docs/season2-plan.md). The gap cover pays when the BTS cause code is not the airline's, and the airline
writes that code. The FAA writes these advisories, in real time, with a stated impacting condition. This module reads the
public advisories database (https://www.fly.faa.gov/adv/advAdvisoryForm), one list page per day and one detail page per
ground stop or ground delay program at a hub, and keeps the parsed result in `data/external/faa/YYYY-MM.json`.

    cd src
    python -m mcp.faa fetch 2018-01 2023-12     # resumable, one request a second
    python -m mcp.faa fetch 2024-01 2026-08
    python -m mcp.faa gate 100                  # prints 100 random programs, raw next to parsed, for the hand check

Times in the advisories are UTC. `programs()` returns one row per advisory with the program period, the kind and the
cause class. The list page is not an official record of every program: it is what the FAA's own database returns.
Politeness. One request per second at most, a descriptive wait after an error, nothing parallel.
"""
from __future__ import annotations

import html as htmllib
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from mcp.ingest import HUBS, ROOT

CACHE = ROOT / "data" / "external" / "faa"
LIST_URL = "https://www.fly.faa.gov/adv/adv_list"
DETAIL_URL = "https://www.fly.faa.gov/adv/adv_otherdis?adv_date={mdy}&advn={advn}"
WAIT = 1.0
KINDS = (("GROUND STOP", "gs"), ("GROUND DELAY PROGRAM", "gdp"))
CAUSES = {"WEATHER": "weather", "VOLUME": "volume", "RUNWAY": "runway_equipment", "RWY-TAXI": "runway_equipment", "EQUIPMENT": "runway_equipment",
          "STAFFING": "staffing", "OTHER": "other"}
PERIOD_KEYS = ("GROUND STOP PERIOD", "CUMULATIVE PROGRAM PERIOD", "GDP CNX PERIOD", "GROUND STOP CNX PERIOD", "GS CNX PERIOD", "ARRIVALS ESTIMATED FOR")
UA = {"User-Agent": "research-script (public data, one request a second)"}


def list_url(d: date) -> str:
    q = {"whichAdvisories": "ATCSCC", "advisoryCategory": "All", "date": d.isoformat(), "airflow": "true", "ctop": "true",
         "gStop": "true", "gDelay": "true", "route": "true", "other": "true"}
    return LIST_URL + "?" + urllib.parse.urlencode(q)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_list(page: str) -> list[dict]:
    """Rows of a day's list page: advisory number, control element, brief title and send time (UTC)."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        cells = [c for c in cells if c != ""]
        m = re.search(r"adv_otherdis\?adv_date=(\d{8})&(?:amp;)?advn=(\d+)", row)
        if len(cells) >= 4 and m and re.fullmatch(r"\d+", cells[0]):
            out.append({"advn": int(m.group(2)), "date": m.group(1), "element": cells[1], "title": cells[3], "send": cells[-1]})
    return out


def wanted(row: dict, hubs=HUBS) -> str | None:
    """'gs' or 'gdp' for a ground stop or ground delay program advisory (including cancellations and revisions) at a hub."""
    airport = row["element"].split("/")[0].strip().upper()
    if airport not in hubs:
        return None
    title = row["title"].upper()
    for needle, kind in KINDS:
        if needle in title:
            return kind
    return None


def _utc(mdy: str, dayhhmm: str, ref: datetime | None = None) -> datetime:
    """'18/2159Z' to a UTC datetime. The advisory's own date (mmddyyyy) places the day: the start is the month, among the
    previous, same and next, in which that day exists and falls closest to the issue date (a stop issued early on the 1st can
    start on the 31st of the month before). With `ref` (the start) the end is the first time at or after `ref` with that day
    number."""
    month, year, issue_day = int(mdy[:2]), int(mdy[4:]), int(mdy[2:4])
    day, hh, mm = int(dayhhmm[:2]), int(dayhhmm[3:5]), int(dayhhmm[5:7])
    issue = datetime(year, month, issue_day, tzinfo=timezone.utc)

    def at(y: int, m: int):
        try:
            return datetime(y, m, day, hh, mm, tzinfo=timezone.utc)
        except ValueError:
            return None

    cands = []
    for dm in (-1, 0, 1):
        n = year * 12 + month - 1 + dm
        c = at(n // 12, n % 12 + 1)
        if c is not None and (ref is None or c >= ref):
            cands.append(c)
    if not cands:
        raise ValueError(f"no valid date for {dayhhmm} near {mdy}")
    return min(cands, key=lambda c: abs((c - issue).total_seconds())) if ref is None else min(cands)


def cause_class(impacting: str | None) -> str:
    """The class of the stated impacting condition ('WEATHER / THUNDERSTORMS' is weather); 'none' when none is stated."""
    cond = (impacting or "").split("/")[0].strip().upper()
    return CAUSES.get(cond, "unknown" if cond else "none")


def parse_detail(page: str, mdy: str, title: str) -> dict:
    """The labelled fields of one advisory. Returns the program period (UTC) when the advisory carries one."""
    i = page.find("ADVZY")
    j = page.find("SIGNATURE", i)
    body = htmllib.unescape(re.sub(r"<[^>]+>", "\n", page[i:j if j > 0 else None]))
    fields = {}
    for line in body.splitlines():
        m = re.match(r"\s*([A-Z][A-Z /,.()+-]*?):\s*(.*)$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2).strip())
    out = {"title": title, "element": fields.get("CTL ELEMENT"), "impacting": fields.get("IMPACTING CONDITION"), "period": None}
    out["cause"] = cause_class(fields.get("IMPACTING CONDITION"))
    for key in PERIOD_KEYS:
        v = fields.get(key)
        m = re.match(r"(\d{2}/\d{4}Z)\s*-\s*(\d{2}/\d{4}Z)", v or "")
        if m:
            start = _utc(mdy, m.group(1))
            end = _utc(mdy, m.group(2), ref=start)
            out["period"] = [start.isoformat(), end.isoformat()]
            out["period_key"] = key
            break
    out.update(title_flags(title))
    return out


def title_flags(title: str) -> dict:
    """What the brief title says about an advisory: a cancellation, a proposal that was not in effect, or a stop that applies
    to one airline's flights (those are the airline's own, not the system's)."""
    t = title.upper()
    return {"cnx": "CNX" in t or "CANCEL" in t, "proposed": "PROPOSED" in t,
            "carrier_specific": ("MAINLINE" in t or "SUB CARRIER" in t or "SUBCARRIER" in t) and "ALL CARRIER" not in t}


def _get(url: str) -> str:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:                                   # a wait and another try; the caller sees a failure only after four
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not read {url}")


def fetch_day(d: date) -> list[dict]:
    rows = parse_list(_get(list_url(d)))
    time.sleep(WAIT)
    out = []
    for r in rows:
        kind = wanted(r)
        if not kind:
            continue
        if title_flags(r["title"])["cnx"]:                   # a cancellation is only needed for when it was sent
            rec = {"title": r["title"], "element": r["element"].split("/")[0], "impacting": None, "period": None, "cause": "none", **title_flags(r["title"])}
        else:
            page = _get(DETAIL_URL.format(mdy=r["date"], advn=r["advn"]))
            time.sleep(WAIT)
            rec = parse_detail(page, r["date"], r["title"])
        rec.update({"day": d.isoformat(), "advn": r["advn"], "kind": kind, "list_element": r["element"], "send": r["send"]})
        out.append(rec)
    return out


def month_path(y: int, m: int) -> Path:
    return CACHE / f"{y}-{m:02d}.json"


def fetch_month(y: int, m: int) -> int:
    path = month_path(y, m)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"month": f"{y}-{m:02d}", "days_done": [], "advisories": []}
    d = date(y, m, 1)
    while d.month == m and d <= date.today() - timedelta(days=1):
        if d.isoformat() not in state["days_done"]:
            state["advisories"].extend(fetch_day(d))
            state["days_done"].append(d.isoformat())
            state["read"] = date.today().isoformat()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=0, ensure_ascii=False), encoding="utf-8", newline="\n")
        d += timedelta(days=1)
    return len(state["advisories"])


def months(start: str, end: str):
    y, m = int(start[:4]), int(start[5:])
    while f"{y}-{m:02d}" <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def programs(start: str = "2018-01", end: str = "2026-08") -> list[dict]:
    out = []
    for y, m in months(start, end):
        p = month_path(y, m)
        if p.exists():
            for a in json.loads(p.read_text(encoding="utf-8"))["advisories"]:
                a["cause"] = cause_class(a.get("impacting"))             # the stored text is the record; the class follows the current mapping
                out.append(a)
    return out


def send_time(text: str) -> datetime:
    """'07/18/19 23:50' (UTC, as the list page prints it) to an aware datetime."""
    return datetime.strptime(text.strip(), "%m/%d/%y %H:%M").replace(tzinfo=timezone.utc)


def active_intervals(advisories: list[dict], hubs=HUBS) -> dict[str, list[tuple[datetime, datetime]]]:
    """Per hub, the merged intervals during which a ground stop or ground delay program written by the FAA was in effect.

    Proposals and stops that apply to one airline's flights are left out. A cancellation advisory ends any earlier
    program of the same kind at that hub that was still running when it was sent. A program that was revised to end earlier
    keeps its original end (revisions are not followed), so intervals can only be too long, never too short."""
    out = {}
    for hub in hubs:
        mine = [a for a in advisories if a.get("element") == hub]
        spans = [[datetime.fromisoformat(a["period"][0]), datetime.fromisoformat(a["period"][1]), a["kind"]]
                 for a in mine if a.get("period") and not a["cnx"] and not a["proposed"] and not a["carrier_specific"]]
        for c in (a for a in mine if a["cnx"] and not a["proposed"] and not a["carrier_specific"]):
            t = send_time(c["send"])
            for sp in spans:
                if sp[2] == c["kind"] and sp[0] <= t < sp[1]:
                    sp[1] = t
        merged = []
        for start, end, _ in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        out[hub] = [(a, b) for a, b in merged]
    return out


def covered(intervals: list[tuple[datetime, datetime]], times) -> "np.ndarray":
    """True for each time (an aware datetime or numpy datetime64) that falls inside one of the merged intervals."""
    import numpy as np
    t = np.asarray(times, dtype="datetime64[s]").astype("int64")
    if not intervals:
        return np.zeros(len(t), bool)
    starts = np.array([a.astimezone(timezone.utc).replace(tzinfo=None) for a, _ in intervals], dtype="datetime64[s]").astype("int64")
    ends = np.array([b.astimezone(timezone.utc).replace(tzinfo=None) for _, b in intervals], dtype="datetime64[s]").astype("int64")
    i = np.searchsorted(starts, t, side="right") - 1
    return (i >= 0) & (t < ends[np.clip(i, 0, None)])


def gate(n: int = 100, seed: int = 0) -> None:
    """The hand check of the plan: n random cached advisories, parsed fields next to the lines they came from."""
    allp = programs()
    random.Random(seed).shuffle(allp)
    for a in allp[:n]:
        page = _get(DETAIL_URL.format(mdy=datetime.fromisoformat(a["day"]).strftime("%m%d%Y"), advn=a["advn"]))
        time.sleep(WAIT)
        raw = htmllib.unescape(re.sub(r"<[^>]+>", "\n", page))
        raw_all = raw
        raw = [l.strip() for l in raw.splitlines() if re.match(r"\s*(CTL ELEMENT|IMPACTING CONDITION|GROUND STOP PERIOD|CUMULATIVE PROGRAM PERIOD|GDP CNX PERIOD|GS CNX PERIOD|GROUND STOP CNX PERIOD)", l)]
        found = re.findall(r"\d\d/\d{4}Z\s*-\s*\d\d/\d{4}Z", re.sub(r"\s+", " ", raw_all))            # every period written anywhere in the advisory
        raw.append("PERIODS_ANYWHERE: " + (" | ".join(found) if found else "none"))
        print(a["day"], a["advn"], a["kind"], "| parsed:", a["element"], a["cause"], a["period"], "| raw:", " ; ".join(raw))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fetch":                                    # fetch START END [K N]: worker K of N takes every N-th month
        k, n = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (0, 1)
        for i, (y, m) in enumerate(months(sys.argv[2], sys.argv[3])):
            if i % n == k:
                print(f"{y}-{m:02d}: {fetch_month(y, m)} advisories", flush=True)
    elif cmd == "gate":
        gate(int(sys.argv[2]) if len(sys.argv) > 2 else 100)
