"""A small HTTP API over the same price table: uvicorn mcp.api:app   (run from src/; docs at /docs).

Endpoints: GET /health, GET /hubs, GET /quote (the original cover, v1), GET /gap-cover and GET /gap-quote (the gap cover
the decision memo recommends, v3, with the frozen v4 loading), GET /model. Read-only, no state, no personal data.
The quote logic lives in mcp.service so the demo page, the command-line tool and this API cannot disagree.
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from mcp.service import MAX_SLACK, MIN_SLACK, PriceService, QuoteError
from mcp.service_gap import MAX_MINUTES, MCT_OPTIONS, MIN_MINUTES, TRAINED_MCT, GapCoverService

app = FastAPI(title="Missed-connection protection pricing",
              description="Illustrative per-connection prices from public data. Costs, loss ratio and price cap are assumptions; "
                          "demand is untested. See the repository README for the validation and its limits.",
              version="1.0")
service = PriceService.from_site()
gap_service = GapCoverService.from_site()


class Quote(BaseModel):
    hub: str
    airline: str
    connection_minutes: int
    bucket: str
    next_flight: str
    p_miss: float
    expected_claim_cost: float
    price: float
    average_fare: float
    price_share_of_fare: float
    share_within_price_cap: float
    decision: Literal["offer", "offer_selectively", "do_not_offer"]
    used_all_airlines_fallback: bool
    sampled_connections: int
    model: dict
    assumptions: dict
    caveats: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cells": len(service.payload["cells"])}


@app.get("/hubs")
def hubs() -> dict:
    return {"hubs": service.hubs, "airlines": service.carriers, "connection_minutes": {"min": MIN_SLACK, "max": MAX_SLACK}}


@app.get("/quote", response_model=Quote)
def quote(hub: str = Query(..., examples=["ORD"]),
          minutes: int = Query(..., ge=MIN_SLACK, le=MAX_SLACK, description="scheduled time between the flights"),
          airline: str | None = Query(None, examples=["UA"]),
          next_flight: Literal["typical", "same", "next"] = "typical") -> dict:
    try:
        return service.quote(hub.upper(), minutes, airline, next_flight)
    except QuoteError as e:
        raise HTTPException(status_code=422, detail=str(e))


class GapQuote(BaseModel):
    product: str
    hub: str
    month: str
    connection_minutes: int
    minimum_connection_minutes: int
    buffer_minutes: int
    model_minutes: int
    bucket: int
    p_overnight_gap: float
    payout: float
    price: float
    price_loaded: float
    loading: float
    average_fare: float
    price_share_of_fare: float
    share_within_price_cap_unloaded: float
    decision: Literal["offer", "offer_selectively", "do_not_offer"]
    share_of_misses_not_airline_coded: dict
    sampled_connections: int
    assumptions: dict
    caveats: list[str]


@app.get("/gap-cover")
def gap_cover() -> dict:
    return {"hubs": gap_service.hubs, "months": gap_service.months, "minimum_connection_minutes": list(MCT_OPTIONS),
            "connection_minutes": {"min": MIN_MINUTES, "max": MAX_MINUTES}, "loading": gap_service.loading,
            "assumptions": gap_service.assumptions}


@app.get("/gap-quote", response_model=GapQuote)
def gap_quote(hub: str = Query(..., examples=["ORD"]),
              minutes: int = Query(..., ge=MIN_MINUTES, le=MAX_MINUTES, description="scheduled time between the flights"),
              month: str = Query(..., examples=["2026-12"], description="month of travel, YYYY-MM"),
              mct: int = Query(TRAINED_MCT, description="the airline's minimum connection time at this airport, minutes")) -> dict:
    try:
        return gap_service.quote(hub.upper(), minutes, month, mct)
    except QuoteError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/model")
def model() -> dict:
    return service.provenance()
