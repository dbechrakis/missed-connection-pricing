# Instructions for working in this repository

This is a public, pre-registered pricing study. Its credibility rests on what was fixed before the data existed. Read `docs/season2-plan.md` for the current plan, `README.md` for the findings, and `VALIDATION.md` for the record. The rules below come from the project's own practice. Breaking one destroys the thing that makes the work believable.

## Standing rules

1. **Sealed months.** No code other than the scheduled job may ingest, build or score BTS months from September 2026 on. The reads in February 2027 (v1 to v4, v5.1) and May 2027 (v5.2) are not part of season 2 and must not be touched, moved or anticipated.
2. **Pre-register before the data is on disk.** For every work package marked "sealed" in the plan, the pre-registration is committed and pushed before the first download of the data it concerns. Tags are added by extending `.github/workflows/preregistration-tags.yml`.
3. **Frozen files stay frozen.** Never edit, reformat or re-save `models/*`, `config/pricing.yaml`, `config/guards.yaml`, any `PREREGISTRATION_*.md`, or Parts 1 to 6 of `VALIDATION.md`. New results go in a new Part 7. A correction goes in the later part, marked as one.
4. **New history lives in new directories.** Put 2018 to 2023 under `data/parquet/ontime_hist/` and `data/parquet/hist_*`. Several modules scan a whole directory. If old months land in `ontime_v3/`, the published numbers stop reproducing.
5. **Do not change `requirements.lock`.** `tests/test_frozen_models.py` fails under another scikit-learn. Prefer numpy over a new dependency. If one is unavoidable, add it pinned and confirm the frozen-model test still passes.
6. **Every number in a document comes from a results file, and a test checks it.** Follow `tests/test_docs.py`. The suite must stay green and must need no data.
7. **Leakage tests come with the feature.** Any forecast, advisory or history feature needs a test showing that changing later information cannot change it.
8. **Report failures as prominently as passes**, in the same commit as the result. Never retune after a read.
9. **House style in documents.** Plain sentences, full stops in place of dashes and semicolons, no number typed by hand. Limits are stated as what was found and what closes the rest.
10. **Branches.** Work on a branch and open a pull request only when the owner asks. Never push to `main` directly.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock   # the pinned versions
.venv/bin/python -m pytest -q                                          # about a minute, needs no data
```

The code is written for Python 3.12 and also passes on 3.13. `pytest.ini` puts `src` on the path, so modules are `mcp.<name>`. Data modules are run from `src/` as `python -m mcp.<name>`. The variant switch `MCP_VARIANT=v3` selects the gap cover's files. Raw data is not in the repository and is not needed by the tests.

## Map

| Path | What it holds |
| --- | --- |
| `src/mcp/` | One module per step. v1 and v2: `ingest`, `connections`, `features`, `model`, `calibration`, `pricing`, `backtest`, `holdout`, `v2`, `monitor`. v3 and v4, the gap cover: `variant`, `causes`, `costs`, `v3`, `v3_audit`, `v3_rolling`, `v3_loading`, `holdout_v3`, `holdout_v4`. v5, self-transfers: `v5`, `v5_1`, `v5_2`. Serving: `service`, `service_gap`, `api`, `score`, `demo`. Grading: `grade`. Season 2: `level`, `risk`, `capital`, `backcast`, `backcast_st`, `coding_audit`, `faa`, `forecast`, `trigger`, `v6`, `gsa_hist`, `demo_risk`, `schedule_features` |
| `tests/` | Hand-built tables with known answers, leakage guards, and checks that documents match `results/` |
| `results/` | Every number quoted anywhere, as JSON or CSV produced by the code |
| `models/` | Frozen artefacts, with hashes recorded in `VALIDATION.md` and the pre-registrations |
| `config/` | Assumptions and guards. Frozen |
| `docs/` | Method, brief, memo, decision log, market evidence, agency inputs, the season 2 plan |
| `site/` | The static demo, built from `results/` by `mcp.demo` |
| `PREREGISTRATION_*.md`, `SCOREBOARD.md` | What was predicted before the data, and how it turned out |

## Where the plan stands

Season 2 work packages are WP0 to WP9 in `docs/season2-plan.md`, whose section 0 says what is done and where it departed from the plan. Data for 2017 to 2023 lives under the variant `MCP_VARIANT=hist` (see `src/mcp/variant.py`), never in the v1 or v3 directories. `requirements-hist.txt` is for `mcp.gsa_hist` only. The forward test of March to August 2027 is `mcp.v6` and `PREREGISTRATION_V6_FORWARD.md`. Record progress in `VALIDATION.md` Part 7, one lettered section per package (7A for WP1, and so on). Stop and report to the owner, without trying alternatives, when a gate in the plan's section 6 is hit.
