#!/usr/bin/env bash
#
# Runs the burst load test while sampling the API container's memory.
#
# The interesting result is not throughput, it is that API memory stays flat
# while hundreds of megabytes of photos are written. That is the empirical proof
# that photo bytes bypass the API tier. If someone later adds a convenient
# "upload through the API" endpoint, this is what catches it.
#
# Usage:  ./scripts/loadtest.sh

set -euo pipefail

cd "$(dirname "$0")/.."

CONTAINER=filmroll-api-1
SAMPLES=/tmp/filmroll-api-mem.txt
PHOTO=/tmp/filmroll-loadtest.jpg

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "error: ${CONTAINER} is not running. Start it with: make up" >&2
  exit 1
fi

# Pillow lives in the image, not necessarily on the host.
if [[ ! -f "$PHOTO" ]]; then
  echo "generating sample photo..."
  docker compose exec -T api python -c "
import io, base64
from PIL import Image
img = Image.new('RGB', (1600, 1200))
px = img.load()
for y in range(0, 1200, 4):
    for x in range(0, 1600, 4):
        c = ((x*255)//1600, (y*255)//1200, (x+y)%255)
        for dy in range(4):
            for dx in range(4):
                px[x+dx, y+dy] = c
buf = io.BytesIO(); img.save(buf, format='JPEG', quality=85)
print(base64.b64encode(buf.getvalue()).decode())
" | python3 -c "import base64,sys,pathlib; pathlib.Path('$PHOTO').write_bytes(base64.b64decode(sys.stdin.read()))"
fi

mem_mb() {
  docker stats --no-stream --format '{{.MemUsage}}' "$CONTAINER" 2>/dev/null \
    | awk '{
        v = $1
        if (v ~ /GiB/) { sub(/GiB/, "", v); print v * 1024 }
        else           { sub(/MiB/, "", v); print v + 0 }
      }'
}

baseline=$(mem_mb)
echo "api memory before: ${baseline} MiB"
echo

: > "$SAMPLES"
(
  while true; do
    mem_mb >> "$SAMPLES" 2>/dev/null || true
    sleep 1
  done
) &
sampler=$!
trap 'kill "$sampler" 2>/dev/null || true' EXIT

set +e
python3 scripts/loadtest.py
result=$?
set -e

kill "$sampler" 2>/dev/null || true
wait "$sampler" 2>/dev/null || true

peak=$(sort -g "$SAMPLES" | tail -1)
after=$(mem_mb)

echo
echo "api memory baseline : ${baseline} MiB"
echo "api memory peak     : ${peak} MiB"
echo "api memory after    : ${after} MiB"
echo
echo "A peak near the baseline means photo bytes never entered the API process."

exit $result
