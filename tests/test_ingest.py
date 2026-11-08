"""Ingest: typing quirks of the BTS CSV and the hub filter."""
import zipfile

import duckdb

from mcp import ingest

HEADER = ",".join(ingest.COLUMNS) + ",Extra,"  # BTS rows end with a trailing comma


def row(date, origin, dest, dep="1200", arr="1400", dep_delay="5.00", cancelled="0.00", diverted="0.00"):
    vals = {"FlightDate": date, "Reporting_Airline": "DL", "Flight_Number_Reporting_Airline": "100",
            "Tail_Number": "N1", "Origin": origin, "Dest": dest, "CRSDepTime": dep, "DepTime": dep,
            "DepDelay": dep_delay, "CRSArrTime": arr, "ArrTime": arr, "ArrDelay": "0.00",
            "Cancelled": cancelled, "CancellationCode": "", "Diverted": diverted,
            "CRSElapsedTime": "120.00", "ActualElapsedTime": "120.00", "Distance": "600.00",
            "CarrierDelay": "12.00", "WeatherDelay": "", "NASDelay": "3.00", "SecurityDelay": "", "LateAircraftDelay": ""}
    return ",".join(vals[c] for c in ingest.COLUMNS) + ",x,"


def make_zip(tmp_path, rows):
    z = tmp_path / "2025_03.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data.csv", "\n".join([HEADER, *rows]) + "\n")
    return z


def test_filter_types_and_cancelled_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "OUT", tmp_path / "out")
    z = make_zip(tmp_path, [
        row("2025-03-01", "ATL", "LAX"),                       # hub origin: kept
        row("2025-03-01", "LAX", "ORD", dep="2400"),           # hub dest: kept, 2400 preserved
        row("2025-03-01", "LAX", "SFO"),                       # no hub: dropped
        row("2025-03-01", "ATL", "JFK", dep="", dep_delay="", cancelled="1.00"),  # cancelled: kept, nulls
    ])
    assert ingest.to_parquet(z, 2025, 3) == 3
    con = duckdb.connect()
    rows = con.execute(f"select * from '{(tmp_path / 'out' / 'year=2025' / 'month=03.parquet').as_posix()}' order by dest").fetchall()
    cols = [d[0] for d in con.description]
    by_dest = {r[cols.index("dest")]: dict(zip(cols, r)) for r in rows}
    assert by_dest["ORD"]["crs_dep_hhmm"] == 2400
    assert by_dest["LAX"]["dep_delay_min"] == 5.0 and by_dest["LAX"]["cancelled"] is False
    assert by_dest["JFK"]["cancelled"] is True and by_dest["JFK"]["dep_hhmm"] is None
    assert not (tmp_path / "2025_03.csv").exists()  # temp CSV cleaned up
    # delay causes: numbers parse, blanks become nulls (BTS leaves them empty unless the flight was 15+ minutes late)
    assert by_dest["LAX"]["delay_carrier_min"] == 12.0 and by_dest["LAX"]["delay_nas_min"] == 3.0
    assert by_dest["LAX"]["delay_weather_min"] is None
