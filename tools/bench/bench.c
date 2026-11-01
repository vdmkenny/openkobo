/* A/B benchmark for the replaced media libraries.
 *
 * Linked by soname, so the same binary runs against the stock or the new
 * libraries depending on the loader's --library-path (see ab.sh). Fonts are
 * rendered the way Qt 5 does it (QFontEngineFT::loadGlyph): load the hinted
 * outline, rasterize into an own buffer with FT_Outline_Get_Bitmap.
 *
 *   bench versions
 *   bench mkcover OUT.jpg            synthetic 1600x2400 cover, quality 85
 *   bench inflate FILE N             zlib uncompress
 *   bench jpeg FILE DENOM N          decode to RGB at 1/DENOM scale
 *   bench ft FONT TEXT PT DPI N      render every character of TEXT
 *   bench xml FILE N                 parse with xmlReadMemory
 *
 * Each workload runs once to warm up, then 5 rounds of N iterations; it prints
 * the best and median time per iteration.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <zlib.h>
#include <jpeglib.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_OUTLINE_H
#include <libxml/parser.h>

static volatile unsigned long sink;

static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static unsigned char *slurp(const char *p, size_t *n)
{
    FILE *f = fopen(p, "rb");
    if (!f) { perror(p); exit(1); }
    fseek(f, 0, SEEK_END); *n = ftell(f); rewind(f);
    unsigned char *b = malloc(*n + 1);
    if (fread(b, 1, *n, f) != *n) { perror(p); exit(1); }
    fclose(f); b[*n] = 0;
    return b;
}

static const char *base(const char *p) { const char *s = strrchr(p, '/'); return s ? s + 1 : p; }

static void bench(const char *name, void (*work)(void), int iters)
{
    double t[5];
    work();
    for (int r = 0; r < 5; r++) {
        double t0 = now();
        for (int i = 0; i < iters; i++) work();
        t[r] = (now() - t0) / iters * 1e3;
    }
    for (int i = 0; i < 5; i++)
        for (int j = i + 1; j < 5; j++)
            if (t[j] < t[i]) { double x = t[i]; t[i] = t[j]; t[j] = x; }
    printf("%-26s best %8.2f ms  median %8.2f ms\n", name, t[0], t[2]);
}

/* zlib */
static unsigned char *zsrc, *zdst; static size_t zn; static const uLongf zcap = 64 << 20;
static void w_inflate(void)
{
    uLongf dl = zcap;
    if (uncompress(zdst, &dl, zsrc, zn) != Z_OK) { puts("inflate failed"); exit(1); }
    sink += dl;
}

/* libjpeg */
static unsigned char *jbuf; static size_t jlen; static int jdenom;
static void w_jpeg(void)
{
    struct jpeg_decompress_struct c; struct jpeg_error_mgr e;
    c.err = jpeg_std_error(&e);
    jpeg_create_decompress(&c);
    jpeg_mem_src(&c, jbuf, jlen);
    jpeg_read_header(&c, TRUE);
    c.scale_num = 1; c.scale_denom = jdenom; c.out_color_space = JCS_RGB;
    jpeg_start_decompress(&c);
    unsigned char *row = malloc(c.output_width * c.output_components);
    while (c.output_scanline < c.output_height) {
        JSAMPROW r = row;
        jpeg_read_scanlines(&c, &r, 1);
        sink += row[0];
    }
    jpeg_finish_decompress(&c); jpeg_destroy_decompress(&c); free(row);
}

/* Smooth colour fields, hard-edged blocks and mild noise: compresses and
 * decodes like a photographic cover rather than a flat test pattern. */
static void mkcover(const char *out)
{
    const int W = 1600, H = 2400;
    unsigned char *row = malloc(W * 3);
    FILE *f = fopen(out, "wb");
    if (!f) { perror(out); exit(1); }
    struct jpeg_compress_struct c; struct jpeg_error_mgr e;
    c.err = jpeg_std_error(&e);
    jpeg_create_compress(&c);
    jpeg_stdio_dest(&c, f);
    c.image_width = W; c.image_height = H; c.input_components = 3; c.in_color_space = JCS_RGB;
    jpeg_set_defaults(&c);
    jpeg_set_quality(&c, 85, TRUE);
    jpeg_start_compress(&c, TRUE);
    srand(1);
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int block = ((x / 230 + y / 310) % 3 == 0 && x % 230 < 170) ? 45 : 0;
            for (int k = 0; k < 3; k++) {
                double v = 120 + 55 * sin(x / (90.0 + 20 * k)) + 40 * cos(y / (50.0 + 15 * k))
                         + 18 * sin((x + y) / (21.0 + 4 * k)) - block * (k - 1) + rand() % 9 - 4;
                row[x * 3 + k] = v < 0 ? 0 : v > 255 ? 255 : (unsigned char)v;
            }
        }
        JSAMPROW r = row;
        jpeg_write_scanlines(&c, &r, 1);
    }
    jpeg_finish_compress(&c); jpeg_destroy_compress(&c); fclose(f); free(row);
}

/* FreeType, Qt 5 glyph path */
static FT_Library ftlib; static unsigned char *fbuf, *text, gbuf[1 << 18];
static size_t fn, tn; static int pt, dpi;
static int qt_glyph(FT_Face f, FT_ULong ch, FT_Bitmap *bm)
{
    if (FT_Load_Glyph(f, FT_Get_Char_Index(f, ch), FT_LOAD_DEFAULT)) return -1;
    FT_GlyphSlot s = f->glyph;
    if (s->format != FT_GLYPH_FORMAT_OUTLINE) return -1;
    FT_BBox cb;
    FT_Outline_Get_CBox(&s->outline, &cb);
    FT_Pos l = cb.xMin & ~63, b = cb.yMin & ~63, r = (cb.xMax + 63) & ~63, t = (cb.yMax + 63) & ~63;
    FT_Outline_Translate(&s->outline, -l, -b);
    memset(bm, 0, sizeof *bm);
    bm->width = (r - l) >> 6; bm->rows = (t - b) >> 6; bm->pitch = (bm->width + 3) & ~3;
    bm->buffer = gbuf; bm->pixel_mode = FT_PIXEL_MODE_GRAY; bm->num_grays = 256;
    memset(gbuf, 0, bm->pitch * bm->rows);
    return FT_Outline_Get_Bitmap(s->library, &s->outline, bm) ? -1 : 0;
}
static void w_ft(void)
{
    FT_Face f;
    if (FT_New_Memory_Face(ftlib, fbuf, fn, 0, &f)) { puts("face failed"); exit(1); }
    FT_Set_Char_Size(f, 0, pt * 64, dpi, dpi);
    FT_Bitmap bm;
    for (size_t i = 0; i < tn; i++) {
        if (qt_glyph(f, text[i], &bm)) { printf("glyph %zu failed\n", i); exit(1); }
        sink += bm.width;
    }
    FT_Done_Face(f);
}

/* libxml2 */
static unsigned char *xbuf; static size_t xn;
static void w_xml(void)
{
    xmlDocPtr d = xmlReadMemory((const char *)xbuf, xn, "chapter.xhtml", NULL, XML_PARSE_NONET);
    if (!d) { puts("parse failed"); exit(1); }
    sink += xmlDocGetRootElement(d) != NULL;
    xmlFreeDoc(d);
}

int main(int argc, char **argv)
{
    const char *m = argc > 1 ? argv[1] : "";
    char name[64];
    if (!strcmp(m, "versions")) {
        FT_Int a, b, c;
        FT_Init_FreeType(&ftlib); FT_Library_Version(ftlib, &a, &b, &c);
        printf("zlib %s, FreeType %d.%d.%d, libxml2 %s\n", zlibVersion(), a, b, c, xmlParserVersion);
    } else if (!strcmp(m, "mkcover") && argc == 3) {
        mkcover(argv[2]);
    } else if (!strcmp(m, "inflate") && argc == 4) {
        zsrc = slurp(argv[2], &zn); zdst = malloc(zcap);
        snprintf(name, sizeof name, "inflate %s", base(argv[2]));
        bench(name, w_inflate, atoi(argv[3]));
    } else if (!strcmp(m, "jpeg") && argc == 5) {
        jbuf = slurp(argv[2], &jlen); jdenom = atoi(argv[3]);
        snprintf(name, sizeof name, "jpeg decode 1/%d", jdenom);
        bench(name, w_jpeg, atoi(argv[4]));
    } else if (!strcmp(m, "ft") && argc == 7) {
        FT_Init_FreeType(&ftlib);
        fbuf = slurp(argv[2], &fn); text = slurp(argv[3], &tn); pt = atoi(argv[4]); dpi = atoi(argv[5]);
        snprintf(name, sizeof name, "render %s", base(argv[2]));
        bench(name, w_ft, atoi(argv[6]));
    } else if (!strcmp(m, "xml") && argc == 4) {
        xmlInitParser(); xbuf = slurp(argv[2], &xn);
        snprintf(name, sizeof name, "parse %s", base(argv[2]));
        bench(name, w_xml, atoi(argv[3]));
    } else {
        fprintf(stderr, "usage: see the comment at the top of bench.c\n");
        return 2;
    }
    return 0;
}
