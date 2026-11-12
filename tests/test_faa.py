"""mcp.faa parses the FAA advisory pages as the FAA writes them (saved pages from 18 July 2019, no network)."""
from datetime import date
from pathlib import Path

import pytest

from mcp import faa

F = Path(__file__).parent / "fixtures" / "faa"
read = lambda n: (F / n).read_text(encoding="utf-8", errors="ignore")


def test_the_list_page_gives_advisories_and_only_hub_ground_stops_and_programs_are_wanted():
    rows = faa.parse_list(read("list_2019-07-18.html"))
    assert len(rows) == 195 and rows[0]["advn"] == 195 and rows[0]["date"] == "07182019"
    wanted = {r["advn"]: faa.wanted(r) for r in rows if faa.wanted(r)}
    assert wanted[178] == "gs" and wanted[180] == "gdp" and wanted[170] == "gdp"
    assert not any(r["element"].startswith(("LGA", "PHL", "EWR")) for r in rows if faa.wanted(r))      # other airports are left out
    assert all(r["element"].split("/")[0] in faa.HUBS for r in rows if faa.wanted(r))


def test_a_ground_stop_is_parsed_to_utc_with_its_stated_cause():
    d = faa.parse_detail(read("detail_07182019_178.html"), "07182019", "ORD/ZAU CDM GROUND STOP")
    assert d["element"] == "ORD" and d["cause"] == "volume" and d["impacting"] == "VOLUME / MULTI-TAXI"
    assert d["period"] == ["2019-07-18T21:59:00+00:00", "2019-07-18T22:30:00+00:00"] and not d["cnx"]


def test_a_program_that_crosses_midnight_ends_the_next_day_and_a_cancellation_is_flagged():
    d = faa.parse_detail(read("detail_07182019_180.html"), "07182019", "CDM GROUND DELAY PROGRAM")
    assert d["period"] == ["2019-07-18T22:22:00+00:00", "2019-07-19T01:59:00+00:00"]
    c = faa.parse_detail(read("detail_07182019_167.html"), "07182019", "CDM GROUND DELAY PROGRAM CNX")
    assert c["cnx"] and c["cause"] == "none" and c["period"][1] == "2019-07-19T13:56:00+00:00"


def test_a_period_that_crosses_a_month_end_moves_to_the_next_month():
    start = faa._utc("01312019", "31/2300Z")
    end = faa._utc("01312019", "01/0200Z", ref=start)
    assert (end.year, end.month, end.day) == (2019, 2, 1)
    dec = faa._utc("12312022", "31/2330Z")
    assert (faa._utc("12312022", "01/0100Z", ref=dec).year, faa._utc("12312022", "01/0100Z", ref=dec).month) == (2023, 1)


def test_titles_say_when_an_advisory_is_a_proposal_or_one_airlines_own_stop():
    assert faa.title_flags("ORD/ZAU AAL MAINLINE AND SUB CARRIER GROUND STOP")["carrier_specific"]
    assert not faa.title_flags("ORD/ZAU CDM GROUND STOP")["carrier_specific"]
    assert faa.title_flags("ATL/ZTL CDM PROPOSED GROUND DELAY PROGRAM")["proposed"]
    assert faa.title_flags("ORD/ZAU ZAU GROUND STOP CANCELATION")["cnx"] and faa.title_flags("X GROUND DELAY PROGRAM CNX")["cnx"]


def test_the_list_address_asks_for_one_day_and_all_the_program_kinds():
    u = faa.list_url(date(2019, 7, 18))
    assert "date=2019-07-18" in u and "gStop=true" in u and "gDelay=true" in u and u.startswith("https://www.fly.faa.gov/adv/adv_list?")


def test_months_enumerates_inclusive_ranges():
    assert list(faa.months("2022-11", "2023-02")) == [(2022, 11), (2022, 12), (2023, 1), (2023, 2)]


def _adv(hub, kind, start, end, send="01/01/19 00:00", cnx=False, proposed=False, carrier_specific=False):
    return {"element": hub, "kind": kind, "period": None if cnx else [start, end], "cnx": cnx, "proposed": proposed,
            "carrier_specific": carrier_specific, "send": send}


def test_intervals_merge_overlaps_drop_proposals_and_airline_stops_and_stop_at_a_cancellation():
    adv = [_adv("ORD", "gs", "2019-07-18T21:59:00+00:00", "2019-07-18T22:30:00+00:00"),
           _adv("ORD", "gs", "2019-07-18T22:20:00+00:00", "2019-07-18T23:00:00+00:00"),           # overlaps: merged
           _adv("ORD", "gdp", "2019-07-18T22:22:00+00:00", "2019-07-19T01:59:00+00:00"),
           _adv("ORD", "gdp", None, None, send="07/18/19 23:30", cnx=True),                       # ends the program at 23:30
           _adv("ORD", "gs", "2019-07-20T10:00:00+00:00", "2019-07-20T11:00:00+00:00", proposed=True),
           _adv("ORD", "gs", "2019-07-21T10:00:00+00:00", "2019-07-21T11:00:00+00:00", carrier_specific=True),
           _adv("ATL", "gs", "2019-07-18T10:00:00+00:00", "2019-07-18T11:00:00+00:00")]
    iv = faa.active_intervals(adv)
    assert [(a.isoformat(), b.isoformat()) for a, b in iv["ORD"]] == [("2019-07-18T21:59:00+00:00", "2019-07-18T23:30:00+00:00")]
    assert len(iv["ATL"]) == 1 and iv["DEN"] == []
    import numpy as np
    t = np.array(["2019-07-18T21:58:00", "2019-07-18T21:59:00", "2019-07-18T23:29:00", "2019-07-18T23:30:00", "2019-07-20T10:30:00"], dtype="datetime64[s]")
    assert faa.covered(iv["ORD"], t).tolist() == [False, True, True, False, False]
    assert not faa.covered([], t).any()


def test_send_time_is_read_as_utc():
    assert faa.send_time("07/18/19 23:50").isoformat() == "2019-07-18T23:50:00+00:00"
