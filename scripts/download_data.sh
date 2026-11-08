#!/usr/bin/env bash
# Downloads the public data the pipeline needs beyond BTS On-Time (which `python -m mcp.ingest` fetches itself).
#
#   DB1B Coupon + Market, 2024 Q1 to 2025 Q2   12 zips from transtats.bts.gov, about 1.95 GB
#   ASOS hourly weather, five hubs              5 CSVs from mesonet.agron.iastate.edu, about 4 MB
#
# Everything lands under data/raw/ (gitignored). Re-running skips files that already exist.
# Usage:  bash scripts/download_data.sh            download
#         bash scripts/download_data.sh --print    only list the URLs
set -euo pipefail
cd "$(dirname "$0")/.."

DB1B_DIR=data/raw/db1b
ASOS_DIR=data/raw/asos
HUBS="ATL ORD DFW DEN CLT"

urls() {
  for t in Coupon Market; do
    for yq in 2024_1 2024_2 2024_3 2024_4 2025_1 2025_2; do
      echo "$DB1B_DIR/${t}_${yq}.zip https://transtats.bts.gov/PREZIP/Origin_and_Destination_Survey_DB1B${t}_${yq}.zip"
    done
  done
  for s in $HUBS; do
    echo "$ASOS_DIR/$s.csv https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=${s}&data=vsby&data=wxcodes&data=p01i&data=sknt&data=gust&year1=2024&month1=1&day1=1&year2=2026&month2=1&day2=1&tz=Etc/UTC&format=onlycomma&latlon=no&missing=empty&trace=T&direct=no&report_type=3&report_type=4"
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
# BTS throttles one connection hard (about 0.2 MB/s) but serves several in parallel; four streams at once.
urls | xargs -P 4 -L 1 bash -c 'fetch "$0" "$1"'
echo "All downloads finished."
