"""
A small PDF writer, standard library only.

Drawing uses a top-left origin and points, which is what layout code wants.
Text is UTF-8 in, embedded as subsetted TrueType (Type0 / Identity-H) with a
ToUnicode map, so it prints exactly and stays selectable and searchable.
"""

import datetime
import hashlib
import zlib

from .fonts import load_font


def _num(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _color_ops(color, stroke):
    """PDF colour operator for a gray level, an (r, g, b) tuple of 0..1, or a 'rrggbb' string."""
    if isinstance(color, str):
        color = tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    if isinstance(color, (int, float)):
        return f"{_num(color)} {'G' if stroke else 'g'}"
    r, g, b = color
    return f"{_num(r)} {_num(g)} {_num(b)} {'RG' if stroke else 'rg'}"


def _text_string(s):
    """A PDF text string: plain ASCII, or UTF-16BE with a byte-order mark."""
    if all(32 <= ord(c) < 127 for c in s):
        return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


class Canvas:
    """One page. y grows downward from the top edge."""

    def __init__(self, doc, width, height):
        self.doc, self.width, self.height = doc, width, height
        self.ops = []

    def _y(self, y):
        return self.height - y

    def save(self):
        self.ops.append("q")

    def restore(self):
        self.ops.append("Q")

    def clip_rect(self, x, y, w, h):
        self.ops.append(f"{_num(x)} {_num(self._y(y + h))} {_num(w)} {_num(h)} re W n")

    def _stroke_style(self, width, dash):
        self.ops.append(f"{_num(width)} w")
        self.ops.append(f"[{' '.join(_num(d) for d in dash)}] 0 d" if dash else "[] 0 d")

    def rect(self, x, y, w, h, fill=None, stroke=None, width=0.5, dash=None):
        self.save()
        if fill is not None:
            self.ops.append(_color_ops(fill, False))
        if stroke is not None:
            self.ops.append(_color_ops(stroke, True))
            self._stroke_style(width, dash)
        op = {(True, True): "B", (True, False): "f", (False, True): "S"}.get((fill is not None, stroke is not None))
        if op:
            self.ops.append(f"{_num(x)} {_num(self._y(y + h))} {_num(w)} {_num(h)} re {op}")
        self.restore()

    def polyline(self, points, stroke=0, width=0.5, dash=None, join="miter"):
        """An open path through (x, y) points."""
        self.save()
        self.ops.append(_color_ops(stroke, True))
        self._stroke_style(width, dash)
        self.ops.append({"miter": "0 j", "round": "1 j"}[join])
        (x0, y0), rest = points[0], points[1:]
        self.ops.append(f"{_num(x0)} {_num(self._y(y0))} m")
        for x, y in rest:
            self.ops.append(f"{_num(x)} {_num(self._y(y))} l")
        self.ops.append("S")
        self.restore()

    def polygon(self, points, fill=0, stroke=None, width=0.5):
        """A closed, filled (and optionally outlined) shape."""
        self.save()
        self.ops.append(_color_ops(fill, False))
        if stroke is not None:
            self.ops.append(_color_ops(stroke, True))
            self._stroke_style(width, None)
        (x0, y0), rest = points[0], points[1:]
        self.ops.append(f"{_num(x0)} {_num(self._y(y0))} m")
        for x, y in rest:
            self.ops.append(f"{_num(x)} {_num(self._y(y))} l")
        self.ops.append("b" if stroke is not None else "f")
        self.restore()

    def line(self, x1, y1, x2, y2, **kw):
        self.polyline([(x1, y1), (x2, y2)], **kw)

    def text(self, x, baseline, s, font="cond", size=9, fill=0):
        """Draw `s` with its left edge at x and its baseline at `baseline`."""
        if not s:
            return
        f = load_font(font)
        gids = [f.glyph_id(c) for c in s]
        self.doc._note_glyphs(font, s, gids)
        res = self.doc._font_resource(font)
        hex_gids = "".join(f"{g:04X}" for g in gids)
        self.ops.append(
            f"BT {_color_ops(fill, False)} /{res} {_num(size)} Tf {_num(x)} {_num(self._y(baseline))} Td <{hex_gids}> Tj ET"
        )


class Document:
    def __init__(self, title="", author="", subject="", creator="netbox-trace-print", created=None):
        self.title, self.author, self.subject, self.creator = title, author, subject, creator
        self.created = created or datetime.datetime.now(datetime.timezone.utc)
        self.pages = []
        self._fonts = {}        # font name -> resource name (F1, F2, ...)
        self._used = {}         # font name -> {gid: first char drawn with it}

    def add_page(self, width, height):
        canvas = Canvas(self, width, height)
        self.pages.append(canvas)
        return canvas

    # -- bookkeeping used by Canvas.text ------------------------------------

    def _font_resource(self, name):
        return self._fonts.setdefault(name, f"F{len(self._fonts) + 1}")

    def _note_glyphs(self, name, text, gids):
        used = self._used.setdefault(name, {})
        for ch, gid in zip(text, gids):
            if gid:
                used.setdefault(gid, ch)

    # -- serialisation -------------------------------------------------------

    def to_bytes(self):
        objects = {}            # id -> bytes
        next_id = [4]           # 1 catalog, 2 pages, 3 info, 4 reserved for resources below

        def alloc():
            next_id[0] += 1
            return next_id[0]

        resources_id = 4

        def stream(dictionary, data, compress=True, extra=""):
            body = zlib.compress(data, 9) if compress else data
            head = f"<< {dictionary}{extra} /Length {len(body)}{' /Filter /FlateDecode' if compress else ''} >>"
            return head.encode() + b"\nstream\n" + body + b"\nendstream"

        font_objects = {}
        for name, res in self._fonts.items():
            font = load_font(name)
            used = self._used.get(name, {})
            subset = font.subset(used.keys())
            tag = "".join(chr(65 + b % 26) for b in hashlib.md5(",".join(map(str, sorted(used))).encode()).digest()[:6])
            base = f"{tag}+{font.postscript_name}"
            scale = 1000.0 / font.units_per_em
            type0, cid, desc, file_, tounicode = (alloc() for _ in range(5))
            font_objects[res] = type0

            widths = " ".join(f"{g} [{_num(font.advances[g] * scale)}]" for g in sorted(used))
            stem_v = 140 if font.weight_class >= 600 else 80
            bbox = " ".join(_num(v * scale) for v in font.bbox)
            objects[type0] = (f"<< /Type /Font /Subtype /Type0 /BaseFont /{base} /Encoding /Identity-H "
                              f"/DescendantFonts [{cid} 0 R] /ToUnicode {tounicode} 0 R >>").encode()
            objects[cid] = (f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{base} "
                            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
                            f"/FontDescriptor {desc} 0 R /DW 0 /W [{widths}] /CIDToGIDMap /Identity >>").encode()
            objects[desc] = (f"<< /Type /FontDescriptor /FontName /{base} /Flags 4 /FontBBox [{bbox}] "
                             f"/ItalicAngle {_num(font.italic_angle)} /Ascent {_num(font.ascent * scale)} "
                             f"/Descent {_num(font.descent * scale)} /CapHeight {_num(font.cap_height * scale)} "
                             f"/StemV {stem_v} /FontFile2 {file_} 0 R >>").encode()
            objects[file_] = stream("", subset, extra=f" /Length1 {len(subset)}")
            objects[tounicode] = stream("", self._to_unicode(used).encode("ascii"))

        objects[resources_id] = ("<< /Font << " + " ".join(f"/{r} {i} 0 R" for r, i in font_objects.items())
                                 + " >> /ProcSet [/PDF /Text] >>").encode()

        page_ids = []
        for canvas in self.pages:
            content = alloc()
            page = alloc()
            objects[content] = stream("", "\n".join(canvas.ops).encode("ascii"))
            objects[page] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_num(canvas.width)} {_num(canvas.height)}] "
                             f"/Resources {resources_id} 0 R /Contents {content} 0 R >>").encode()
            page_ids.append(page)

        stamp = self.created.strftime("D:%Y%m%d%H%M%S+00'00'")
        info = f"<< /Title {_text_string(self.title)} /Author {_text_string(self.author)} " \
               f"/Subject {_text_string(self.subject)} /Creator {_text_string(self.creator)} " \
               f"/Producer {_text_string(self.creator)} /CreationDate ({stamp}) >>"
        objects[1] = b"<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /DisplayDocTitle true >> >>"
        objects[2] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()
        objects[3] = info.encode("ascii")

        out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for oid in sorted(objects):
            offsets[oid] = len(out)
            out += f"{oid} 0 obj\n".encode() + objects[oid] + b"\nendobj\n"
        xref = len(out)
        size = max(objects) + 1
        out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
        for oid in range(1, size):
            out += f"{offsets[oid]:010d} 00000 n \n".encode()
        file_id = hashlib.md5(bytes(out)).hexdigest()
        out += (f"trailer\n<< /Size {size} /Root 1 0 R /Info 3 0 R /ID [<{file_id}> <{file_id}>] >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)

    @staticmethod
    def _to_unicode(used):
        lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
                 "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
                 "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def",
                 "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange"]
        items = sorted(used.items())
        for i in range(0, len(items), 100):
            chunk = items[i:i + 100]
            lines.append(f"{len(chunk)} beginbfchar")
            lines += [f"<{gid:04X}> <{ch.encode('utf-16-be').hex().upper()}>" for gid, ch in chunk]
            lines.append("endbfchar")
        lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
        return "\n".join(lines)
