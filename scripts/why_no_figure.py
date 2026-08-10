"""Which gate rejected a figure on a page. No model call - detection is pure PyMuPDF.

    python why_no_figure.py "tests/eval/figures/pdfs/EPSENS TRANSITION CLIMAT - 810571.pdf" 1
"""
import sys
import fitz
from tablerag.ingestion import layout as L

pdf, pageno = sys.argv[1], int(sys.argv[2])
page = fitz.open(pdf)[pageno - 1]


def r(box):
    return "[%4.0f %4.0f %4.0f %4.0f]" % (box.x0, box.y0, box.x1, box.y1)


table_rects = []
for table, _grid in L.detect_tables(page):
    table_rects.append(fitz.Rect(table.bbox))
print(f"ACCEPTED TABLES: {len(table_rects)}")
for tr in table_rects:
    print("   ", r(tr))

print("\nVECTOR CLUSTERS (each gate, in the order production applies them)")
marks = L._drawing_marks(page)
clusters = L.cluster_rects(marks) if marks else []
aside = [box for box, count in clusters
         if count < L._VEC_MIN_PATHS
         or box.width < L._VEC_MIN_WIDTH or box.height < L._VEC_MIN_HEIGHT]
for box, count in sorted(clusters, key=lambda c: (c[0].y0, c[0].x0)):
    why = None
    if count < L._VEC_MIN_PATHS:
        why = f"too few paths ({count} < {L._VEC_MIN_PATHS})"
    elif box.width < L._VEC_MIN_WIDTH or box.height < L._VEC_MIN_HEIGHT:
        why = f"too small ({box.width:.0f}x{box.height:.0f})"
    else:
        box = L.with_legend(box, count, aside)
        ious = [L._iou(box, tr) for tr in table_rects]
        if any(v > L._VEC_TABLE_IOU for v in ious):
            why = f"IS a table (IoU {max(ious):.2f} > {L._VEC_TABLE_IOU})"
        elif L.looks_like_table_striping([m for m in marks if box.contains(m)]):
            why = "looks_like_table_striping"
        elif L.drawn_around_text(page, box, table_rects):
            prose = []
            for block in page.get_text("blocks"):
                if block[6] != 0 or not box.contains(fitz.Rect(block[:4])):
                    continue
                text = " ".join(str(block[4] or "").split())
                if (len(text) >= L._PROSE_MIN_CHARS
                        and text.count(" ") >= L._PROSE_MIN_SPACES):
                    prose.append(text)
            if prose:
                why = f"PROSE: {prose[0][:90]!r}"
            else:
                inside = [tr for tr in table_rects if (box & tr).get_area() > 0]
                cov = sum((box & tr).get_area() for tr in inside)
                uni = box.get_area() + sum(tr.get_area() for tr in inside) - cov
                why = f"table cover {cov / uni:.2f} > {L._VEC_MAX_TABLE_COVER}"
    print(f"  {r(box)} paths={count:4}  {why or 'KEPT'}")

print("\nWHAT THE EVAL SEES (analyze_page, every region in order)")
regions = L.analyze_page(page, dpi=150, min_chars=100).regions
for region in regions:
    print(f"  {region.type:6} {r(fitz.Rect(region.bbox))} "
          f"vector={getattr(region, 'vector', False)} ctx={region.context[:40]!r}")

figs = [x for x in regions if x.type == "figure"]
print(f"\nfigure indices the eval can address: 0..{len(figs) - 1}")
for i, f in enumerate(figs):
    print(f"  #{i} {r(fitz.Rect(f.bbox))} bars={len(f.bars)} palette={len(f.palette)}")
