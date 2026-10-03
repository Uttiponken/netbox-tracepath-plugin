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
        rows = [list(range(i, min(i + n, len(plans)))) for i in range(0, len(plans), n)]

        row_info = []
        for idxs in rows:
            hdr = max(plans[i].hdr_h for i in idxs)
            ports = max(plans[i].ports_h for i in idxs)
            det = max(plans[i].det_h for i in idxs)
            conn = hdr + m.lh * 1.5 - 0.1 * size            # connector y, from the top of the row
            # cable names stand above the in-row connectors, so the connector must be low enough for them
            for i in idxs[:-1]:
                conn = max(conn, self._names_h(m, doc.links[i], gw - 6, False) + 4)
            h = hdr + ports + det
            # the details hanging under each in-row connector must fit inside the row
            for i in idxs[:-1]:
                h = max(h, conn + 4 + self._details_h(m, doc.links[i], gw - 6, False) + PAD)
            row_info.append({"idxs": idxs, "hdr": hdr, "ports": ports, "det": det, "h": h, "conn": conn})

        # the cable between the last block of a row and the first of the next: name above the line,
        # details below it, and clear space above and below the whole thing
        ret_h = {}
        for r, info in enumerate(row_info[:-1]):
            link = doc.links[info["idxs"][-1]]
            ret_h[r] = (RET_PAD + self._names_h(m, link, avail, True) + 6
                        + self._details_h(m, link, avail, True) + RET_PAD)

        # header and footer heights
        head_first, head_next, foot = self._header_heights(m, content_w)
        top_first, top_next = self.margin + head_first, self.margin + head_next
        bottom = self.page_h - self.margin - foot

        placements, page, y, fits = [], 0, top_first, True
        for r, info in enumerate(row_info):
            def need(starts):
                # the region above a row that continues from the previous page holds one extra caption line
                cont = ret_h[r - 1] + m.lh if (starts and r > 0) else 0
                # a row that is followed by a page break needs one extra caption line too, so reserve it
                # when checking the fit (but only advance by the real gap)
                return cont, cont + info["h"] + (ret_h[r] + m.lh if r in ret_h else 0)
            starts = not placements or placements[-1]["page"] != page
            cont, total = need(starts)
            if y + total > bottom and placements and placements[-1]["page"] == page:
                page += 1
                y = top_next
                cont, total = need(True)
            if y + total > bottom:
                fits = False
            placements.append({"page": page, "y": y + cont, "cont": cont, "row": r})
            y += cont + info["h"] + (ret_h[r] if r in ret_h else 0)
        return {"m": m, "n": n, "bw": bw, "gw": gw, "avail": avail, "plans": plans, "rows": row_info,
                "ret_h": ret_h, "placements": placements, "fits": fits, "label_w": label_w,
                "top_first": top_first, "top_next": top_next, "bottom": bottom, "pages": page + 1,
                "head_first": head_first, "head_next": head_next, "foot": foot}

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
        painters = []
        for p in range(plan["pages"]):
            canvas = pdf.add_page(self.page_w, self.page_h)
            painters.append(_Painter(canvas, p, m, report))
            self._page_chrome(painters[p], plan, p)

        for place in plan["placements"]:
            self._draw_row(painters, plan, place)
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

    def _draw_row(self, painters, plan, place):
        m, n, bw, gw, avail = plan["m"], plan["n"], plan["bw"], plan["gw"], plan["avail"]
        info = plan["rows"][place["row"]]
        pt = painters[place["page"]]
        c, doc = pt.c, self.doc
        y, h = place["y"], info["h"]
        x0 = self.margin + GUTTER
        left_x, right_x = self.margin + GUTTER / 2, self.page_w - self.margin - GUTTER / 2
        conn_y = y + info["conn"]

        for col, i in enumerate(info["idxs"]):
            self._draw_block(pt, plan, doc.blocks[i], plan["plans"][i], x0 + col * (bw + gw), y, h, info)

        # connectors inside the row: name above the line, details below it
        for col, i in enumerate(info["idxs"][:-1]):
            bx = x0 + col * (bw + gw) + bw
            self._cable_line(c, doc.links[i], [(bx, conn_y), (bx + gw, conn_y)])
            self._names_above(pt, m, doc.links[i], bx + gw / 2, gw - 6, conn_y - 3, False)
            self._details_below(pt, m, doc.links[i], bx + 3, conn_y + 4, gw - 6, False)

        # the cable out of this row, back under it and into the first block of the next row (or the next page)
        r = place["row"]
        if r in plan["ret_h"]:
            link = doc.links[info["idxs"][-1]]
            end_x = x0 + (len(info["idxs"]) - 1) * (bw + gw) + bw
            names_h = self._names_h(m, link, avail, True)
            line_y = y + h + RET_PAD + names_h + 3
            nxt = plan["placements"][r + 1]
            nxt_info = plan["rows"][r + 1]
            same_page = nxt["page"] == place["page"]
            path = [(end_x, conn_y), (right_x, conn_y), (right_x, line_y), (left_x, line_y)]
            self._names_above(pt, m, link, x0 + avail / 2, avail, line_y - 3, True)
            if same_page:
                path += [(left_x, nxt["y"] + nxt_info["conn"]), (x0, nxt["y"] + nxt_info["conn"])]
                self._cable_line(c, link, path)
                self._details_below(pt, m, link, x0, line_y + 4, avail, True)
            else:
                self._cable_line(c, link, path)
                c.polygon([(left_x - 4, line_y), (left_x + 4, line_y), (left_x, line_y + 8)], fill=0)
                self._details_below(pt, m, link, x0, line_y + 4, avail, True)
                caption_y = line_y + 4 + self._details_h(m, link, avail, True) + 2
                pt.text(x0 + avail / 2, caption_y, f"Continues on page {nxt['page'] + 1}", True, align="center")

        # arriving from the previous page
        if place["cont"]:
            prev = plan["rows"][r - 1]
            link = doc.links[prev["idxs"][-1]]
            top = y - place["cont"]
            conn = y + info["conn"]
            self._cable_line(c, link, [(left_x, top), (left_x, conn), (x0, conn)])
            c.polygon([(left_x - 4, top + 2), (left_x + 4, top + 2), (left_x, top + 9)], fill=0)
            pt.text(x0 + avail / 2, top + 3, f"Continued from page {plan['placements'][r - 1]['page'] + 1}", True,
                    align="center")
            names_h = self._names_h(m, link, avail, True)
            self._names_above(pt, m, link, x0 + avail / 2, avail, top + 3 + m.lh + names_h, True)
            self._details_below(pt, m, link, x0, top + 3 + m.lh + names_h + 3, avail, True)

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
