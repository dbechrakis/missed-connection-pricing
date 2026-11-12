#!/usr/bin/env bash
# Public data for the 2018 to 2023 backcast (PREREGISTRATION_V6_BACKCAST.md), beyond the BTS On-Time files that
# `MCP_VARIANT=hist python -m mcp.ingest` fetches itself.
#
#   DB1B Coupon + Market, 2017 Q1 to 2022 Q4   48 zips from transtats.bts.gov, about 4.5 GB (the previous year prices each month)
#   ASOS hourly weather, five hubs, 2018 to 2023   5 CSVs from mesonet.agron.iastate.edu
#
# Lands under data/raw/ (gitignored). Re-running skips files that already exist.
# Usage:  bash scripts/download_hist.sh            download
#         bash scripts/download_hist.sh --print    only list the URLs
set -euo pipefail
cd "$(dirname "$0")/.."

DB1B_DIR=data/raw/db1b
ASOS_DIR=data/raw/asos_hist
HUBS="ATL ORD DFW DEN CLT"

urls() {
  for t in Coupon Market; do
    for y in 2017 2018 2019 2020 2021 2022; do
      for q in 1 2 3 4; do
        echo "$DB1B_DIR/${t}_${y}_${q}.zip https://transtats.bts.gov/PREZIP/Origin_and_Destination_Survey_DB1B${t}_${y}_${q}.zip"
      done
    done
  done
  for s in $HUBS; do
    echo "$ASOS_DIR/$s.csv https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=${s}&data=vsby&data=wxcodes&data=p01i&data=sknt&data=gust&year1=2018&month1=1&day1=1&year2=2024&month2=1&day2=1&tz=Etc/UTC&format=onlycomma&latlon=no&missing=empty&trace=T&direct=no&report_type=3&report_type=4"
  done
}

if [[ "${1:-}" == "--print" ]]; then urls; exit 0; fi

mkdir -p "$DB1B_DIR" "$ASOS_DIR"
fetch() {  # fetch <dest> <url>: download to a .part file and rename, so an interrupted run never leaves a truncated file
  local dest="$1" url="$2"
  [[ -s "$dest" ]] && { echo "skip $dest"; return; }
  curl -fsS --retry 3 -C - -o "$dest.part" "$url" && mv "$dest.part" "$dest" && echo "done $dest"
}
export -f fetch
urls | xargs -P 4 -L 1 bash -c 'fetch "$0" "$1"'
echo "All downloads finished."
