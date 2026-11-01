#!/bin/sh
# A/B benchmark of the stock and the new media libraries under ARM emulation.
# Usage: tools/bench/run.sh <official kobo-update zip>
# Needs out/libs (make libs) and Docker with linux/arm/v7 emulation (Docker
# Desktop has it; on Linux, qemu-user-static). Results: out/bench/results.txt.
set -eu
ZIP=$1
cd "$(dirname "$0")/../.."
OUT=out/bench

python3 -I tools/bench/prep.py --zip "$ZIP" --out "$OUT"
mkdir -p "$OUT/new"
cp out/libs/overlay/lib/* out/libs/overlay/usr/lib/* "$OUT/new/"

# Compile against the new libraries' headers; the binary goes to stdout so the
# container user needs no write access to the host directory.
docker run --rm -v "$PWD/tools/bench:/src:ro" openkobo-libs sh -c '
	S=/home/builder/stage
	arm-kobo-linux-gnueabihf-gcc -O2 -Wall -o /tmp/bench /src/bench.c \
		-I$S/include -I$S/include/freetype2 -I$S/include/libxml2 \
		-L$S/lib -lz -ljpeg -lfreetype -lxml2 -lm -lrt >&2 && cat /tmp/bench' > "$OUT/bench"
chmod 755 "$OUT/bench"

docker run --rm --platform linux/arm/v7 -v "$PWD/tools/bench/ab.sh:/ab.sh:ro" \
	-v "$PWD/$OUT:/b" busybox:1.36.1 sh /ab.sh | tee "$OUT/results.txt"
