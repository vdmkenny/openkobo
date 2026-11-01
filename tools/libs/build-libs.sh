#!/bin/sh
# Cross-build the media/parsing libraries against the koxtoolchain and verify
# that each one keeps the stock soname, gains no dependency the device lacks,
# and needs no glibc newer than the device's 2.11.1. Runs inside the Docker
# image (see Dockerfile). Output: /opt/out/lib.
set -eu

HOST=arm-kobo-linux-gnueabihf
STAGE=/home/builder/stage
OUT=/home/builder/out
SRC=/home/builder/src
JOBS="$(nproc)"
export CC="$HOST-gcc" AR="$HOST-ar" RANLIB="$HOST-ranlib"
export PKG_CONFIG_PATH="$STAGE/lib/pkgconfig"
export CPPFLAGS="-I$STAGE/include" LDFLAGS="-L$STAGE/lib"

# Device's glibc floor. A build that needs anything newer is rejected.
MAX_GLIBC=2.11.1
# Shared libraries that already exist on the device; a NEEDED outside this set
# (plus the libraries we build here) would be unresolvable on the device.
DEVICE_LIBS="libc.so.6 libm.so.6 libdl.so.2 librt.so.1 libpthread.so.0 libgcc_s.so.1 libstdc++.so.6 ld-linux-armhf.so.3"

ZLIB=1.3.1 PNG=1.6.44 TURBO=3.0.4 FT=2.13.3 XML2=2.13.5

mkdir -p "$SRC" "$STAGE" "$OUT/lib"
cd "$SRC"
get() { wget -q "$1" -O "$2"; }

# zlib -> libz.so.1 (zlib's configure is bespoke; it honours $CC)
get https://github.com/madler/zlib/releases/download/v${ZLIB}/zlib-${ZLIB}.tar.gz z.tgz
tar xf z.tgz && cd "zlib-${ZLIB}"
./configure --prefix="$STAGE" --shared
make -j"$JOBS"; make install
cd "$SRC"

# libpng -> libpng16.so.16 (links the zlib built above)
get https://downloads.sourceforge.net/project/libpng/libpng16/${PNG}/libpng-${PNG}.tar.xz p.txz
tar xf p.txz && cd "libpng-${PNG}"
./configure --host="$HOST" --prefix="$STAGE" --disable-static
make -j"$JOBS"; make install
cd "$SRC"

# libjpeg-turbo -> libjpeg.so.62 (classic API soname; WITH_JPEG8=0)
get https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/${TURBO}/libjpeg-turbo-${TURBO}.tar.gz j.tgz
tar xf j.tgz && mkdir -p "libjpeg-turbo-${TURBO}/b" && cd "libjpeg-turbo-${TURBO}/b"
cmake -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=arm \
      -DCMAKE_C_COMPILER="$HOST-gcc" -DCMAKE_INSTALL_PREFIX="$STAGE" \
      -DCMAKE_INSTALL_LIBDIR=lib -DENABLE_STATIC=0 -DWITH_JPEG8=0 ..
make -j"$JOBS"; make install
cd "$SRC"

# FreeType -> libfreetype.so.6. Stock links only libc/libgcc_s, so keep every
# optional dependency off to avoid adding NEEDED entries.
get https://downloads.sourceforge.net/project/freetype/freetype2/${FT}/freetype-${FT}.tar.xz f.txz
tar xf f.txz && cd "freetype-${FT}"
./configure --host="$HOST" --prefix="$STAGE" --disable-static \
      --with-zlib=no --with-png=no --with-harfbuzz=no --with-brotli=no --with-bzip2=no
make -j"$JOBS"; make install
cd "$SRC"

# libxml2 -> libxml2.so.2. Stock links only libdl/libm/libc; keep extras off.
get https://download.gnome.org/sources/libxml2/2.13/libxml2-${XML2}.tar.xz x.txz
tar xf x.txz && cd "libxml2-${XML2}"
./configure --host="$HOST" --prefix="$STAGE" --disable-static \
      --without-python --without-lzma --without-zlib --without-icu
make -j"$JOBS"; make install
cd "$SRC"

# Collect the real shared objects (follow the soname symlinks to the files).
cp -a "$STAGE"/lib/libz.so.* "$STAGE"/lib/libpng16.so.* "$STAGE"/lib/libjpeg.so.* \
      "$STAGE"/lib/libfreetype.so.* "$STAGE"/lib/libxml2.so.* "$OUT/lib/" 2>/dev/null || true
rm -f "$OUT"/lib/*.la

echo "============================================================"
echo "verification (glibc floor ${MAX_GLIBC}, device libs: ${DEVICE_LIBS})"
echo "============================================================"
fail=0
newest_glibc() {
    "$HOST-readelf" -V "$1" 2>/dev/null | grep -oE 'GLIBC_[0-9]+(\.[0-9]+)+' \
        | sed 's/GLIBC_//' | sort -V | tail -1
}
ver_le() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }
for so in "$OUT"/lib/*.so.*; do
    [ -f "$so" ] || continue
    case "$so" in *.py) continue;; esac
    name="$(basename "$so")"
    soname="$("$HOST-readelf" -d "$so" | sed -n 's/.*SONAME.*\[\(.*\)\]/\1/p')"
    g="$(newest_glibc "$so")"; [ -n "$g" ] || g=0.0
    printf '\n%s  (SONAME %s)\n' "$name" "$soname"
    printf '  max glibc: %s' "$g"
    if ver_le "$g" "$MAX_GLIBC"; then echo "  OK"; else echo "  TOO NEW"; fail=1; fi
    for dep in $("$HOST-readelf" -d "$so" | sed -n 's/.*NEEDED.*\[\(.*\)\]/\1/p'); do
        ok=no
        for d in $DEVICE_LIBS libz.so.1 libpng16.so.16 libjpeg.so.62 libfreetype.so.6 libxml2.so.2; do
            [ "$dep" = "$d" ] && ok=yes
        done
        printf '  NEEDED %s  %s\n' "$dep" "$([ $ok = yes ] && echo ok || echo 'UNRESOLVED')"
        [ $ok = yes ] || fail=1
    done
done
echo
[ $fail -eq 0 ] || { echo "VERIFICATION FAILED"; exit 1; }

# Assemble the device overlay tree: each real .so named by its soname, at the
# stock directory, so the device's NEEDED <soname> resolves straight to it and
# the result does not depend on base-image symlinks.
mkdir -p "$OUT/overlay/lib" "$OUT/overlay/usr/lib"
cp -L "$STAGE/lib/libz.so.1"        "$OUT/overlay/lib/libz.so.1"
cp -L "$STAGE/lib/libpng16.so.16"   "$OUT/overlay/lib/libpng16.so.16"
cp -L "$STAGE/lib/libjpeg.so.62"    "$OUT/overlay/lib/libjpeg.so.62"
cp -L "$STAGE/lib/libfreetype.so.6" "$OUT/overlay/usr/lib/libfreetype.so.6"
cp -L "$STAGE/lib/libxml2.so.2"     "$OUT/overlay/usr/lib/libxml2.so.2"
echo "ALL OK"
