"""CI gate: a running API container must answer exactly what the code answers, and report the frozen hashes.

    PYTHONPATH=src python scripts/check_container.py http://127.0.0.1:8000

Queries every hub x airline (and all airlines) x several connection times x the three next-flight cases, compares each
JSON answer with mcp.service directly, checks invalid input is refused, and checks /model's SHA-256 values are the
ones frozen in VALIDATION.md. Exits 1 on any difference. Standard library only.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.service import PriceService

ROOT = Path(__file__).resolve().parents[1]


def get(base: str, path: str, **params):
    url = f"{base}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main(base: str) -> int:
    svc, errors, checked = PriceService.from_site(), [], 0
    for hub in svc.hubs:
        for airline in [None, *svc.carriers[hub]]:
            for minutes in (45, 59, 60, 90, 150, 225):
                for nxt in ("typical", "same", "next"):
                    params = {"hub": hub, "minutes": minutes, "next_flight": nxt, **({"airline": airline} if airline else {})}
                    status, body = get(base, "/quote", **params)
                    want = json.loads(json.dumps(svc.quote(hub, minutes, airline, nxt)))
                    checked += 1
                    if status != 200 or body != want:
                        errors.append(f"{params}: status {status}, differs from the core")
    for bad in ({"hub": "ORD", "minutes": 30}, {"hub": "XXX", "minutes": 60}, {"hub": "ORD", "minutes": 60, "next_flight": "soon"}):
        status, _ = get(base, "/quote", **bad)
        if status != 422:
            errors.append(f"{bad} should be refused with 422, got {status}")
    status, model = get(base, "/model")
    validation = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    for name, h in model.get("artefact_sha256", {}).items():
        if not h or h not in validation:
            errors.append(f"/model reports {name} hash {h}, not the one frozen in VALIDATION.md")
    print(f"{checked} quotes compared, {len(errors)} problems")
    for e in errors[:20]:
        print("  ", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
