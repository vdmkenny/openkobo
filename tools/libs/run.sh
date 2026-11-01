#!/bin/sh
# Build the media libraries in Docker and copy them to out/libs/.
# The first run also builds the cross-toolchain and takes a long time; later
# runs reuse the cached toolchain layer. Requires a running Docker engine.
set -eu
cd "$(dirname "$0")"
REPO=$(cd ../.. && pwd)
IMAGE=openkobo-libs
OUT="$REPO/out/libs"

echo "Building $IMAGE (first run builds the toolchain; this is slow)..."
docker build --progress=plain -t "$IMAGE" .

echo "Extracting libraries to $OUT ..."
rm -rf "$OUT"; mkdir -p "$OUT"
cid=$(docker create "$IMAGE")
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
docker cp "$cid:/home/builder/out/." "$OUT/"

echo
echo "Built libraries ($OUT/lib):"
ls -l "$OUT/lib"
echo
echo "Device overlay ($OUT/overlay) — pass to the build with --overlay:"
find "$OUT/overlay" -type f | sed "s#$OUT/##"
