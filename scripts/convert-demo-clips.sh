#!/usr/bin/env bash
# Convert the 6 demo clip videos (apps/web/test-results/**/video.webm) into GIFs under
# docs/assets/ via the two-pass palette (fps=10, 880px). Run AFTER:
#   cd apps/web && pnpm exec playwright test e2e/demo.spec.ts
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$ROOT/apps/web/test-results"
ASSETS="$ROOT/docs/assets"
TMP="$(mktemp -d)"

MAP=(
  "demo-hero:demo"
  "demo-clip-1-launch-resolve:clip-launch-resolve"
  "demo-clip-2-live-cockpit:clip-live-cockpit"
  "demo-clip-3-beat-graph-ga:clip-beat-graph-ga"
  "demo-clip-4-make-it-yours:clip-make-it-yours"
  "demo-clip-5-quality-export:clip-quality-export"
)

for pair in "${MAP[@]}"; do
  slug="${pair%%:*}"; out="${pair##*:}"
  webm="$(find "$RESULTS" -path "*${slug}*" -name '*.webm' | head -1)"
  if [ -z "$webm" ]; then echo "MISSING webm for $slug" >&2; exit 1; fi
  ffmpeg -y -i "$webm" -vf "fps=10,scale=880:-1:flags=lanczos,palettegen=stats_mode=diff" "$TMP/$out.png" -loglevel error
  ffmpeg -y -i "$webm" -i "$TMP/$out.png" -filter_complex \
    "fps=10,scale=880:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" \
    "$ASSETS/$out.gif" -loglevel error
  echo "wrote $ASSETS/$out.gif ($(du -h "$ASSETS/$out.gif" | cut -f1))"
done
rm -rf "$TMP"
