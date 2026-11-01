#!/usr/bin/env python3
"""Prepare inputs for the library benchmark (tools/bench/run.sh).

From the official update zip: the firmware's glibc and loader (rt/), the stock
libraries named by soname (stock/), and two Kobo fonts (data/). Kobo stores
fonts Qt-compressed: "QTD", 4-byte big-endian length, zlib stream.

Text: Python's own documentation (pydoc_data), as an EPUB-style XHTML
chapter, its deflate stream, and a 4000-character page for glyph rendering.

Usage: python3 -I tools/bench/prep.py --zip kobo-update-*.zip --out out/bench
"""

import argparse
import html
import io
import re
import tarfile
import zipfile
import zlib
from pathlib import Path

# soname -> pattern of the versioned file the update ships in lib/ or usr/lib/
RUNTIME = {
    "ld.so": r"lib/ld-[\d.]+\.so",
    "libc.so.6": r"lib/libc-[\d.]+\.so",
    "libm.so.6": r"lib/libm-[\d.]+\.so",
    "libdl.so.2": r"lib/libdl-[\d.]+\.so",
    "libpthread.so.0": r"lib/libpthread-[\d.]+\.so",
    "librt.so.1": r"lib/librt-[\d.]+\.so",
    "libgcc_s.so.1": r"lib/libgcc_s\.so\.1",
}
STOCK = {
    "libz.so.1": r"lib/libz\.so\.1\.[\d.]+",
    "libjpeg.so.62": r"lib/libjpeg\.so\.62\.[\d.]+",
    "libfreetype.so.6": r"usr/lib/libfreetype\.so\.6\.[\d.]+",
    "libxml2.so.2": r"usr/lib/libxml2\.so\.2\.[\d.]+",
}
FONTS = ("georgia.ttf", "OpenDyslexic-Regular.otf")


def resolve(tf, members, path):
    m = members[path]
    while m.issym():
        m = members[path.rpartition("/")[0] + "/" + m.linkname]
    return tf.extractfile(m).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    for d in ("rt", "stock", "data"):
        (args.out / d).mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.zip) as zf:
        blob = zf.read("KoboRoot.tgz")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        members = {m.name.removeprefix("./"): m for m in tf.getmembers()}
        for sub, table in (("rt", RUNTIME), ("stock", STOCK)):
            for soname, pattern in table.items():
                hits = [p for p in members if re.fullmatch(pattern, p)]
                if len(hits) != 1:
                    raise SystemExit(f"{soname}: expected one match for {pattern}, got {hits}")
                dst = args.out / sub / soname
                dst.write_bytes(resolve(tf, members, hits[0]))
                dst.chmod(0o755)
        for name in FONTS:
            path = next(p for p in members if p.endswith("/fonts/" + name))
            raw = resolve(tf, members, path)
            if raw[:3] != b"QTD":
                raise SystemExit(f"{name}: not a Qt-compressed font")
            (args.out / "data" / name).write_bytes(zlib.decompress(raw[7:]))
            if name == "georgia.ttf":
                (args.out / "data" / "georgia.z").write_bytes(raw[7:])

    from pydoc_data.topics import topics
    text = "\n\n".join(topics[k] for k in sorted(topics))
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if len(p) > 40]
    body = []
    for i, p in enumerate(paras):
        if i % 25 == 0:
            body.append(f'<h2 id="s{i}">Section {i // 25 + 1}</h2>')
        words = html.escape(p, quote=False).split(" ")
        if len(words) > 8:
            words[3] = f"<em>{words[3]}</em>"
            words[7] = f'<span class="c{i % 4}">{words[7]}</span>'
        body.append("<p>" + " ".join(words) + "</p>")
    xhtml = ('<?xml version="1.0" encoding="utf-8"?>\n'
             '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
             '<head><title>Chapter</title><link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
             "<body>\n" + "\n".join(body) + "\n</body>\n</html>\n").encode()
    data = args.out / "data"
    (data / "chapter.xhtml").write_bytes(xhtml)
    (data / "chapter.z").write_bytes(zlib.compress(xhtml, 6))
    page = "".join(c for c in " ".join(paras) if 32 <= ord(c) < 127)[:4000]
    (data / "page.txt").write_text(page)


if __name__ == "__main__":
    main()
