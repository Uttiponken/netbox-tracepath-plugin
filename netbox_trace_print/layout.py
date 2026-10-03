"""
The layout engine: a TraceDoc in, a PDF out.

Blocks sit on a uniform grid and flow left to right like text. When a row is
full the next block starts on the next row, and the cable between them is drawn
as a line that leaves the right side of the last block, runs back under the row
and enters the left side of the first block of the next row. When a page is
full the trace continues on the next page, with "continues on / continued from"
markers carrying the cable that crosses the break.

Everything is measured with the real font, so all text wraps inside its block
and nothing is cut off. If a single row cannot fit on a page the font shrinks
step by step down to `min_size`; if it still cannot, the report says so.
Pure Python, no Django.
"""

from dataclasses import dataclass, field

from .pdf.fonts import load_font
from .pdf.paper import MM, page_size
from .pdf.writer import Document

PAD = 4.0          # inside a block
GUTTER = 14.0      # left and right of the grid, where the return lines run
RET_PAD = 12.0     # clear space between a return line and the blocks above and below it
TIP = 12.0         # depth of the chevron's point and notch
CHEV_MIN_H = 44.0  # a chevron marker is never lower than this
LINE_BLACK = 0
SOFT = 0.28        # captions and secondary text: dark enough to stay readable in black and white
HEADER_FILL = 0.9


@dataclass
class LayoutSpec:
    paper: str = "A4"
    orientation: str = "landscape"
    margin_mm: float = 12.0
    base_size: float = 8.0          # body text, points
    min_size: float = 7.0           # never smaller than this
    columns: int = 0                # 0 = as many as fit
    min_block_width: float = 140.0
    font: str = "cond"
    bold: str = "cond-bold"


@dataclass
class LayoutReport:
    pages: int = 0
    columns: int = 0
    font_size: float = 0.0
    fits: bool = True
    warnings: list = field(default_factory=list)
    boxes: list = field(default_factory=list)         # (page, x0, y0, x1, y1) of every text run, for tests
    block_boxes: list = field(default_factory=list)   # the same for every block frame
    chevron_boxes: list = field(default_factory=list)  # (page, kind, x0, y0, x1, y1, text) of every chevron marker


class Metrics:
    """Text measuring and wrapping for one font size."""

    def __init__(self, spec, size):
        self.size, self.spec = size, spec
        self.regular, self.heavy = load_font(spec.font), load_font(spec.bold)
        self.lh = size * 1.25
        f = self.regular
        self.asc, self.desc = f.ascent / f.units_per_em, -f.descent / f.units_per_em

    def font(self, bold):
        return self.spec.bold if bold else self.spec.font

    def width(self, text, bold=False, size=None):
        f = self.heavy if bold else self.regular
        return f.text_width(text, size or self.size)

    def baseline(self, top, size=None, lh=None):
        size, lh = size or self.size, lh or self.lh
        return top + (lh - size * (self.asc + self.desc)) / 2 + size * self.asc

    def wrap(self, text, width, bold=False, size=None):
        """Lines of `text` no wider than `width`; breaks at spaces, then after - / _ . : , then anywhere."""
        out = []
        for para in str(text).split("\n"):
            line = ""
            for word in para.split(" "):
                trial = word if not line else f"{line} {word}"
                if self.width(trial, bold, size) <= width:
                    line = trial
                    continue
                if line:
                    out.append(line)
                    line = ""
                if self.width(word, bold, size) <= width:
                    line = word
                    continue
                pieces = self._break(word, width, bold, size)
                out += pieces[:-1]
                line = pieces[-1]
            out.append(line)
        return out or [""]

    def _break(self, word, width, bold, size):
        pieces, cur, last = [], "", 0
        for ch in word:
            if cur and self.width(cur + ch, bold, size) > width:
                cut = last if last else len(cur)
                pieces.append(cur[:cut])
                cur, last = cur[cut:], 0
            cur += ch
            if ch in "-/_.:,":
                last = len(cur)
        return pieces + [cur]


class _Painter:
    """Draws on a page and records every text run's box so tests can check nothing escapes."""

    def __init__(self, canvas, page_no, m, report):
        self.c, self.page_no, self.m, self.report = canvas, page_no, m, report

    def text(self, x, top, s, bold=False, size=None, fill=0, lh=None, align="left", width=None):
        size = size or self.m.size
        lh = lh or self.m.lh
        w = self.m.width(s, bold, size)
        if align == "right":
            x = x - w
        elif align == "center":
            x = x - w / 2
        self.c.text(x, self.m.baseline(top, size, lh), s, self.m.font(bold), size, fill)
        self.report.boxes.append((self.page_no, x, top, x + w, top + lh))
        return w


class _BlockPlan:
    pass


class Engine:
    def __init__(self, doc, spec):
        self.doc, self.spec = doc, spec
        self.page_w, self.page_h = page_size(spec.paper, spec.orientation)
        self.margin = spec.margin_mm * MM

    # -- planning ------------------------------------------------------------

    def run(self):
        sizes, s = [], self.spec.base_size
        while s >= self.spec.min_size - 1e-9:
            sizes.append(s)
            s -= 0.5
        # Prefer the roomiest layout: at each font size try the natural column count, then fewer, wider
        # columns (wider blocks wrap less, so they get shorter), and only then a smaller font.
        for size in sizes:
            plan = self._plan(size)
            for cols in range(plan["n"] - 1, 0, -1):
                if plan["fits"] or self.spec.columns:
                    break
                plan = self._plan(size, cols)
            if plan["fits"]:
                break
        else:
            plan = self._plan(self.spec.min_size, 1 if not self.spec.columns else None)
        return self._draw(plan)

    def _plan(self, size, cols=None):
        m = Metrics(self.spec, size)
        spec, doc = self.spec, self.doc
        content_w = self.page_w - 2 * self.margin
        avail = content_w - 2 * GUTTER

        # gap between columns: wide enough for the widest cable title
        cables = [c for lk in doc.links for c in lk.cables]
        title_w = max((m.width(c.title, True) for c in cables), default=0) + 10 + 6      # swatch + padding
        item_w = max((m.width(f"{f.label}: {f.value}") for c in cables for f in c.fields), default=0)
        gw = min(100.0, max(62.0, title_w, min(92.0, item_w) + 6) + 8)
        n = max(1, min(len(doc.blocks), cols or spec.columns or 0)) if (cols or spec.columns) else 0
        if not n:
            n = 1
            while len(doc.blocks) > n and (avail - n * gw) / (n + 1) >= spec.min_block_width:
                n += 1
        n = max(1, n)
        bw = (avail - (n - 1) * gw) / n if n > 1 else min(avail, 460.0)

        label_w = self._label_width(m, bw)
        plans = [self._plan_block(m, b, bw, label_w) for b in doc.blocks]

        head_first, head_next, foot = self._header_heights(m, content_w)
        top_first, top_next = self.margin + head_first, self.margin + head_next
        bottom = self.page_h - self.margin - foot

        # Pages are built one at a time: take as many blocks as fit. A page that continues an earlier one
        # starts with a chevron marker (a cell like any other), and one that continues on a later page
        # ends with one. The cable that crosses the break is drawn on both sides of it.
        pages, i, fits, total = [], 0, True, len(doc.blocks)
        while i < total or not pages:
            p = len(pages)
            top = top_first if p == 0 else top_next
            chosen = None
            for count in range(max(total - i, 1), 0, -1):
                layout = self._layout_page(m, self._cells(m, i, count, p, bw), n, plans, gw, avail, top, bottom)
                if layout["fits"]:
                    chosen = (count, layout)
                    break
            if chosen is None:
                fits = False
                chosen = (1, layout)
            pages.append(chosen[1])
            i += chosen[0]
        return {"m": m, "n": n, "bw": bw, "gw": gw, "avail": avail, "plans": plans, "pages_layout": pages,
                "fits": fits, "label_w": label_w, "pages": len(pages), "foot": foot}

    # -- pages made of cells ---------------------------------------------------

    def _chevron(self, m, kind, neighbour, page, bw):
        """A chevron marker. `neighbour` is the block on the other side of the page break."""
        blk = self.doc.blocks[neighbour]
        if kind == "in":
            caption = f"Continued from page {page}"
            port = blk.ports[-1].out_name if blk.ports else ""
        else:
            caption = f"Continues on page {page + 2}"
            port = blk.ports[0].in_name if blk.ports else ""
        text_w = bw - 2 * TIP - 2 * PAD
        lines = [(t, True, 0) for t in m.wrap(caption, text_w, True)]
        lines += [(t, True, 0) for t in m.wrap(f"{blk.title} : {port}" if port else blk.title, text_w, True)]
        place = " · ".join(x for x in (blk.site, blk.rack) if x)
        if place:
            lines += [(t, False, SOFT) for t in m.wrap(place, text_w)]
        return {"kind": kind, "idx": neighbour, "lines": lines, "out": neighbour if kind == "in" else None,
                "h": max(CHEV_MIN_H, len(lines) * m.lh + 2 * PAD)}

    def _cells(self, m, first, count, page, bw):
        total = len(self.doc.blocks)
        cells = [self._chevron(m, "in", first - 1, page, bw)] if page > 0 else []
        cells += [{"kind": "block", "idx": j, "out": j if j < total - 1 else None} for j in range(first, first + count)]
        if first + count < total:
            cells.append(self._chevron(m, "out", first + count, page, bw))
        return cells

    def _row_info(self, m, cells, plans, gw):
        doc = self.doc
        blocks = [c for c in cells if c["kind"] == "block"]
        hdr = max((plans[c["idx"]].hdr_h for c in blocks), default=0)
        ports = max((plans[c["idx"]].ports_h for c in blocks), default=0)
        det = max((plans[c["idx"]].det_h for c in blocks), default=0)
        chev_h = max((c["h"] for c in cells if c["kind"] != "block"), default=0)
        conn = hdr + m.lh * 1.5 - 0.1 * m.size if blocks else 0           # connector y, from the top of the row
        conn = max(conn, chev_h / 2 + 2)
        links = [doc.links[a["out"]] for a in cells[:-1]]
        for link in links:                          # cable names stand above the connector
            conn = max(conn, self._names_h(m, link, gw - 6, False) + 4)
        h = max(hdr + ports + det, conn + chev_h / 2 + 2 if chev_h else 0)
        for link in links:                          # the details hanging under it must fit inside the row
            h = max(h, conn + 4 + self._details_h(m, link, gw - 6, False) + PAD)
        return {"cells": cells, "hdr": hdr, "ports": ports, "det": det, "h": h, "conn": conn}

    def _layout_page(self, m, cells, n, plans, gw, avail, top, bottom):
        doc = self.doc
        y, rows = top, []
        chunks = [cells[k:k + n] for k in range(0, len(cells), n)] or [[]]
        for r, chunk in enumerate(chunks):
            info = self._row_info(m, chunk, plans, gw)
            info["y"], info["ret"] = y, 0.0
            y += info["h"]
            if r < len(chunks) - 1:                 # the cable from this row's last cell to the next row's first
                link = doc.links[chunk[-1]["out"]]
                info["ret"] = (RET_PAD + self._names_h(m, link, avail, True) + 6
                               + self._details_h(m, link, avail, True) + RET_PAD)
                y += info["ret"]
            rows.append(info)
        return {"rows": rows, "fits": y <= bottom + 1e-6, "cells": cells}

    def _label_width(self, m, bw):
        inner = bw - 2 * PAD
        widest = max((m.width(f.label, True) for b in self.doc.blocks for f in b.fields), default=0)
        return min(widest + 6, inner * 0.42)

    def _port_lines(self, m, name, fields, width):
        lines = [(t, True) for t in m.wrap(name, width, True)] if name else []
        for f in fields:
            lines += [(t, False) for t in m.wrap(f"{f.label}: {f.value}" if f.label else f.value, width)]
        return lines

    def _plan_block(self, m, block, bw, label_w):
        p = _BlockPlan()
        inner = bw - 2 * PAD
        tsize = m.size + 1.5
        tlh = tsize * 1.25
        p.title = m.wrap(block.title, inner, True, tsize)
        p.sub = m.wrap(block.subtitle, inner) if block.subtitle else []
        p.tlh, p.tsize = tlh, tsize
        p.hdr_h = PAD + len(p.title) * tlh + len(p.sub) * m.lh + PAD

        half = (inner - 8) / 2
        p.rows = []
        h = m.lh                                           # IN / OUT caption line
        for row in block.ports:
            left = self._port_lines(m, row.in_name, row.in_fields, half)
            right = self._port_lines(m, row.out_name, row.out_fields, half)
            p.rows.append((left, right))
            h += max(len(left), len(right)) * m.lh
        p.ports_h = h + PAD if block.ports else 0

        vw = inner - label_w - 4
        p.det = []
        h = 0
        for f in block.fields:
            lab = m.wrap(f.label, label_w, True)
            val = m.wrap(f.value, vw)
            p.det.append((lab, val))
            h += max(len(lab), len(val)) * m.lh
        p.det_h = h + 2 * PAD if block.fields else 0
        return p

    def _cable_parts(self, m, cable, width, wide):
        """(name lines, detail lines) for one cable. The name is drawn above the cable, the details below it."""
        names = m.wrap(cable.title, width - (10 if cable.color_hex else 0), True)
        items = [f"{f.label}: {f.value}" if f.label else f.value for f in cable.fields]
        if cable.color_name:
            items.insert(0, f"Colour: {cable.color_name}")
        details = []
        if wide:                                   # a wide line: flow the items, separated by dots
            cur = ""
            for item in items:
                trial = item if not cur else f"{cur}   ·   {item}"
                if m.width(trial) <= width:
                    cur = trial
                else:
                    if cur:
                        details.append(cur)
                    wrapped = m.wrap(item, width)
                    details += wrapped[:-1]
                    cur = wrapped[-1]
            if cur:
                details.append(cur)
        else:                                      # a narrow gap: one item per line
            for item in items:
                details += m.wrap(item, width)
        return names, details

    def _names_h(self, m, link, width, wide):
        return sum(len(self._cable_parts(m, c, width, wide)[0]) for c in link.cables) * m.lh

    def _details_h(self, m, link, width, wide):
        return sum(len(self._cable_parts(m, c, width, wide)[1]) for c in link.cables) * m.lh

    def _header_text(self, m, content_w):
        doc = self.doc
        return {
            "title": m.wrap(doc.title, content_w, True, 14),
            "summary": [t for s in doc.summary for t in m.wrap(s, content_w)],
            "notes": [m.wrap(n, content_w - 16) for n in doc.notes],
            "running": m.wrap(doc.title, content_w, True, 9),
        }

    def _header_heights(self, m, content_w):
        t = self._header_text(m, content_w)
        first = len(t["title"]) * 18.0 + 2 + 3 + len(t["summary"]) * m.lh + 3
        first += sum(len(n) * m.lh + 4 + 4 for n in t["notes"]) + 6
        nxt = len(t["running"]) * 12.0 + 6
        return first, nxt, 16.0

    # -- drawing --------------------------------------------------------------

    def _draw(self, plan):
        m, doc = plan["m"], self.doc
        report = LayoutReport(pages=plan["pages"], columns=plan["n"], font_size=m.size, fits=plan["fits"])
        if not plan["fits"]:
            report.warnings.append(
                f"A row of blocks is taller than a {self.spec.paper} {self.spec.orientation} page at "
                f"{self.spec.min_size:g} pt. Choose larger paper or fewer fields.")
        pdf = Document(title=doc.title, author="netbox-trace-print")
        for p, page in enumerate(plan["pages_layout"]):
            pt = _Painter(pdf.add_page(self.page_w, self.page_h), p, m, report)
            self._page_chrome(pt, plan, p)
            for r, info in enumerate(page["rows"]):
                self._draw_row(pt, plan, page["rows"], r)
        return pdf.to_bytes(), report

    def _page_chrome(self, pt, plan, p):
        m, c, doc = plan["m"], pt.c, self.doc
        x0, x1 = self.margin, self.page_w - self.margin
        head = self._header_text(m, x1 - x0)
        if p == 0:
            y = self.margin
            for line in head["title"]:
                pt.text(x0, y, line, True, 14, lh=18)
                y += 18
            y += 2
            c.line(x0, y, x1, y, stroke=0, width=1.0)
            y += 3
            for line in head["summary"]:
                pt.text(x0, y, line)
                y += m.lh
            y += 3
            for lines in head["notes"]:
                h = len(lines) * m.lh + 4
                c.rect(x0, y, x1 - x0, h, stroke=0, width=0.8, dash=(3, 2))
                for i, t in enumerate(lines):
                    pt.text(x0 + 8, y + 2 + i * m.lh, t)
                y += h + 4
        else:
            for k, line in enumerate(head["running"]):
                pt.text(x0, self.margin + k * 12, line, True, 9, lh=12)
            ry = self.margin + len(head["running"]) * 12 + 1
            c.line(x0, ry, x1, ry, stroke=0, width=0.6)
        fy = self.page_h - self.margin - plan["foot"] + 2
        c.line(x0, fy, x1, fy, stroke=0, width=0.4)
        pt.text(x0, fy + 2, doc.footer, size=7, lh=9, fill=SOFT)
        pt.text(x1, fy + 2, f"Page {p + 1} of {plan['pages']}", True, 7, lh=9, align="right")

    def _draw_row(self, pt, plan, rows, r):
        m, bw, gw, avail = plan["m"], plan["bw"], plan["gw"], plan["avail"]
        info = rows[r]
        c, doc = pt.c, self.doc
        y, h = info["y"], info["h"]
        x0 = self.margin + GUTTER
        left_x, right_x = self.margin + GUTTER / 2, self.page_w - self.margin - GUTTER / 2
        conn_y = y + info["conn"]
        cells = info["cells"]

        def cx(col):
            return x0 + col * (bw + gw)

        for col, cell in enumerate(cells):
            if cell["kind"] == "block":
                self._draw_block(pt, plan, doc.blocks[cell["idx"]], plan["plans"][cell["idx"]], cx(col), y, h, info)
            else:
                self._draw_chevron(pt, m, cell, cx(col), bw, conn_y)

        def entry(col):                            # where a cable enters a cell: a chevron's notch is inside it
            return cx(col) + (TIP if cells[col]["kind"] == "out" else 0)

        # connectors inside the row: name above the line, details below it
        for col in range(len(cells) - 1):
            link = doc.links[cells[col]["out"]]
            xa, xb = cx(col) + bw, entry(col + 1)
            self._cable_line(c, link, [(xa, conn_y), (xb, conn_y)])
            mid = (xa + cx(col + 1)) / 2
            self._names_above(pt, m, link, mid, gw - 6, conn_y - 3, False)
            self._details_below(pt, m, link, xa + 3, conn_y + 4, gw - 6, False)

        # the cable from this row's last cell, back under the row and into the first cell of the next row
        if r < len(rows) - 1:
            link = doc.links[cells[-1]["out"]]
            nxt = rows[r + 1]
            end_x = cx(len(cells) - 1) + bw
            line_y = y + h + RET_PAD + self._names_h(m, link, avail, True) + 3
            into = nxt["cells"][0]
            path = [(end_x, conn_y), (right_x, conn_y), (right_x, line_y), (left_x, line_y),
                    (left_x, nxt["y"] + nxt["conn"]), (x0 + (TIP if into["kind"] == "out" else 0), nxt["y"] + nxt["conn"])]
            self._cable_line(c, link, path)
            self._names_above(pt, m, link, x0 + avail / 2, avail, line_y - 3, True)
            self._details_below(pt, m, link, x0, line_y + 4, avail, True)

    def _draw_chevron(self, pt, m, cell, x0, bw, conn_y):
        """A marker where the trace continues on another page: a chevron pointing in the direction of travel."""
        h, x1 = cell["h"], x0 + bw
        top, bottom = conn_y - h / 2, conn_y + h / 2
        pt.c.polygon([(x0, top), (x1 - TIP, top), (x1, conn_y), (x1 - TIP, bottom), (x0, bottom), (x0 + TIP, conn_y)],
                     fill=HEADER_FILL, stroke=0, width=1.0)
        pt.report.chevron_boxes.append((pt.page_no, cell["kind"], x0, top, x1, bottom,
                                        " ".join(t for t, _b, _f in cell["lines"])))
        ty = conn_y - len(cell["lines"]) * m.lh / 2
        for text, bold, fill in cell["lines"]:
            pt.text(x0 + bw / 2, ty, text, bold, fill=fill, align="center")
            ty += m.lh

    def _cable_line(self, c, link, points):
        for k, cable in enumerate(link.cables):
            off = k * 4.0
            pts = [(x, y + off) for x, y in points]
            if cable.color_hex:
                c.polyline(pts, stroke=0, width=3.0, join="round")
                c.polyline(pts, stroke=cable.color_hex, width=1.6, join="round")
            else:
                c.polyline(pts, stroke=0, width=1.4, join="round")

    def _names_above(self, pt, m, link, cx, width, bottom, wide):
        """The cable names, centred on cx and ending at `bottom`, with the colour swatch before each name."""
        lines = [(c, t) for c in link.cables for t in self._cable_parts(m, c, width, wide)[0]]
        top = bottom - len(lines) * m.lh
        for k, (cable, text) in enumerate(lines):
            w = m.width(text, True)
            if cable.color_hex and k == [c for c, _ in lines].index(cable):
                pt.c.rect(cx - w / 2 - 10, top + k * m.lh + 2.5, 7, 5, fill=cable.color_hex, stroke=0, width=0.6)
            pt.text(cx, top + k * m.lh, text, True, align="center")

    def _details_below(self, pt, m, link, x, top, width, wide):
        """The cable details from `top` down: left-aligned in a narrow gap, centred on a wide line."""
        for cable in link.cables:
            for text in self._cable_parts(m, cable, width, wide)[1]:
                if wide:
                    pt.text(x + width / 2, top, text, align="center")
                else:
                    pt.text(x, top, text)
                top += m.lh

    def _draw_block(self, pt, plan, block, bp, bx, y, h, info):
        m, bw = plan["m"], plan["bw"]
        c = pt.c
        pt.report.block_boxes.append((pt.page_no, bx, y, bx + bw, y + h))
        c.rect(bx, y, bw, h, fill=1, stroke=0, width=0.9)
        c.rect(bx, y, bw, info["hdr"], fill=HEADER_FILL, stroke=0, width=0.9)
        ty = y + PAD
        for line in bp.title:
            pt.text(bx + PAD, ty, line, True, bp.tsize, lh=bp.tlh)
            ty += bp.tlh
        for line in bp.sub:
            pt.text(bx + PAD, ty, line, fill=SOFT)
            ty += m.lh

        py = y + info["hdr"]
        if bp.rows:
            c.line(bx + PAD, py + m.lh, bx + bw - PAD, py + m.lh, stroke=0.6, width=0.4)
            pt.text(bx + PAD, py, "IN", True, fill=SOFT)
            pt.text(bx + bw - PAD, py, "OUT", True, fill=SOFT, align="right")
            ry = py + m.lh
            for left, right in bp.rows:
                ly = ry
                for text, bold in left:
                    pt.text(bx + PAD, ly, text, bold)
                    ly += m.lh
                ly = ry
                for text, bold in right:
                    pt.text(bx + bw - PAD, ly, text, bold, align="right")
                    ly += m.lh
                ry += max(len(left), len(right)) * m.lh
        if bp.det:
            dy = y + info["hdr"] + info["ports"]
            c.line(bx, dy, bx + bw, dy, stroke=0, width=0.5)
            ry = dy + PAD
            for lab, val in bp.det:
                for k, t in enumerate(lab):
                    pt.text(bx + PAD, ry + k * m.lh, t, True)
                for k, t in enumerate(val):
                    pt.text(bx + PAD + plan["label_w"] + 4, ry + k * m.lh, t)
                ry += max(len(lab), len(val)) * m.lh
        # frame last so the borders sit on top of the fills
        c.rect(bx, y, bw, h, stroke=0, width=0.9)
        c.line(bx, y + info["hdr"], bx + bw, y + info["hdr"], stroke=0, width=0.6)


def render(doc, spec=None):
    """TraceDoc -> (pdf bytes, LayoutReport)."""
    return Engine(doc, spec or LayoutSpec()).run()
