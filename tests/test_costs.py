"""Sourced overnight costs: the GSA page parser on the real table layout, and the fiscal-year arithmetic."""
import pytest

from mcp.costs import fiscal_year, overnight_cost, parse_page

# The structure of gsa.gov's per-diem result page (trimmed to the two tables the parser reads)
PAGE = """
<table><caption>Daily lodging rates (excluding taxes) | <span>October 2025 - September 2026</span></caption>
<thead><tr><th>Primary destination</th><th>County</th><th>2025 Oct</th></tr></thead>
<tbody><tr><td>Atlanta</td><td>Fulton / Dekalb</td><td>$182</td><td>$182</td><td>$182</td><td>$197</td><td>$197</td><td>$197</td>
<td>$182</td><td>$182</td><td>$182</td><td>$182</td><td>$182</td><td>$182</td></tr>
<tr><td>Standard Rate</td><td>Applies for all locations without specified rates</td><td>$110</td></tr></tbody></table>
<table id='perdiem-meals-breakdown' class='stripedTable table_perdiem'><caption>Meals</caption><thead><tr><th>x</th></tr></thead>
<tbody><tr><td>Atlanta</td><td>Fulton / Dekalb</td><td class="x">$86</td><td>$22</td><td>$23</td><td>$36</td><td>$5</td><td>$64.50</td></tr></tbody></table>
"""


def test_parser_reads_the_destination_row_not_the_standard_rate():
    p = parse_page(PAGE)
    assert p["city"] == "Atlanta" and p["county"] == "Fulton / Dekalb" and p["standard_rate"] is False
    assert p["lodging"][10] == 182 and p["lodging"][1] == 197 and p["lodging"][9] == 182 and len(p["lodging"]) == 12
    assert p["mie"] == 86


def test_fiscal_year_runs_october_to_september():
    assert fiscal_year(2025, 9) == 2025 and fiscal_year(2025, 10) == 2026 and fiscal_year(2026, 1) == 2026


def test_overnight_cost_is_lodging_for_the_month_plus_meals():
    p = parse_page(PAGE)
    table = {"ATL": {2026: p}}
    assert overnight_cost(table, "ATL", 2026, 2) == pytest.approx(197 + 86)      # February 2026 is in FY2026
    assert overnight_cost(table, "ATL", 2025, 11) == pytest.approx(182 + 86)     # November 2025 is in FY2026
    with pytest.raises(KeyError):
        overnight_cost(table, "ATL", 2026, 11)                                   # November 2026 is FY2027: not in this table
