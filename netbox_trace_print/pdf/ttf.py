"""
Minimal TrueType reader and subsetter, standard library only.

It reads exactly what a PDF needs from a .ttf file: glyph advance widths, the
Unicode -> glyph mapping and the outlines. Subsetting keeps every glyph id
unchanged (the glyphs a document does not use are emptied), so the PDF can
address glyphs directly by id and needs no cmap table in the embedded font.
"""

import struct


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class TTFont:
    def __init__(self, data):
        self.data = data
        self.tables = {}
        num_tables = _u16(data, 4)
        for i in range(num_tables):
            tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            self.tables[tag.decode("latin-1")] = (offset, length)

        head = self._table("head")
        self.units_per_em = _u16(head, 18)
        self.bbox = tuple(_i16(head, o) for o in (36, 38, 40, 42))
        self.loca_long = _i16(head, 50) == 1

        hhea = self._table("hhea")
        self.ascent = _i16(hhea, 4)
        self.descent = _i16(hhea, 6)
        self._num_hmetrics = _u16(hhea, 34)

        self.num_glyphs = _u16(self._table("maxp"), 4)
        self.advances = self._read_advances()
        # A subset (see subset()) carries only the glyph tables; the descriptive tables are optional.
        self.cmap = self._read_cmap() if "cmap" in self.tables else {}
        self.italic_angle = struct.unpack_from(">i", self._table("post"), 4)[0] / 65536.0 if "post" in self.tables else 0.0
        if "OS/2" in self.tables:
            os2 = self._table("OS/2")
            self.weight_class = _u16(os2, 4)
            self.cap_height = _i16(os2, 88) if _u16(os2, 0) >= 2 else int(self.ascent * 0.7)
        else:
            self.weight_class, self.cap_height = 400, int(self.ascent * 0.7)
        self.postscript_name = (self._read_name(6) if "name" in self.tables else None) or "DejaVuSans"

    # -- tables ------------------------------------------------------------

    def _table(self, tag):
        offset, length = self.tables[tag]
        return memoryview(self.data)[offset:offset + length]

    def _read_advances(self):
        hmtx = self._table("hmtx")
        advances = [_u16(hmtx, 4 * i) for i in range(self._num_hmetrics)]
        advances += [advances[-1]] * (self.num_glyphs - self._num_hmetrics)
        return advances

    def _read_name(self, name_id):
        name = self._table("name")
        count, string_offset = _u16(name, 2), _u16(name, 4)
        for i in range(count):
            platform, _enc, _lang, nid, length, offset = struct.unpack_from(">6H", name, 6 + 12 * i)
            if nid == name_id and platform == 3:
                raw = bytes(name[string_offset + offset:string_offset + offset + length])
                return raw.decode("utf-16-be")
        return None

    def _read_cmap(self):
        cmap = self._table("cmap")
        subtables = []
        for i in range(_u16(cmap, 2)):
            platform, encoding, offset = struct.unpack_from(">HHI", cmap, 4 + 8 * i)
            subtables.append((platform, encoding, offset))
        # Prefer full Unicode (format 12), then BMP (format 4)
        for wanted in ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3), (0, 0)):
            for platform, encoding, offset in subtables:
                if (platform, encoding) == wanted:
                    mapping = self._parse_cmap_subtable(cmap, offset)
                    if mapping:
                        return mapping
        raise ValueError("no usable Unicode cmap in font")

    @staticmethod
    def _parse_cmap_subtable(cmap, offset):
        fmt = _u16(cmap, offset)
        mapping = {}
        if fmt == 4:
            seg_count = _u16(cmap, offset + 6) // 2
            end_o = offset + 14
            start_o = end_o + 2 * seg_count + 2
            delta_o = start_o + 2 * seg_count
            range_o = delta_o + 2 * seg_count
            for s in range(seg_count):
                end, start = _u16(cmap, end_o + 2 * s), _u16(cmap, start_o + 2 * s)
                delta, range_off = _i16(cmap, delta_o + 2 * s), _u16(cmap, range_o + 2 * s)
                for code in range(start, end + 1):
                    if code == 0xFFFF:
                        continue
                    if range_off == 0:
                        gid = (code + delta) & 0xFFFF
                    else:
                        pos = range_o + 2 * s + range_off + 2 * (code - start)
                        gid = _u16(cmap, pos)
                        if gid:
                            gid = (gid + delta) & 0xFFFF
                    if gid:
                        mapping[code] = gid
        elif fmt == 12:
            for g in range(struct.unpack_from(">I", cmap, offset + 12)[0]):
                start, end, gid = struct.unpack_from(">III", cmap, offset + 16 + 12 * g)
                for code in range(start, end + 1):
                    mapping[code] = gid + (code - start)
        return mapping

    # -- measuring ---------------------------------------------------------

    def glyph_id(self, char):
        return self.cmap.get(ord(char), 0)

    def text_width(self, text, size):
        """Width in points of `text` at font size `size` (no kerning, as in the PDF)."""
        total = sum(self.advances[self.glyph_id(c)] for c in text)
        return total * size / self.units_per_em

    # -- subsetting --------------------------------------------------------

    def _glyph_ranges(self):
        loca = self._table("loca")
        if self.loca_long:
            offsets = [_u32(loca, 4 * i) for i in range(self.num_glyphs + 1)]
        else:
            offsets = [2 * _u16(loca, 2 * i) for i in range(self.num_glyphs + 1)]
        return offsets

    def _components(self, glyph):
        """Glyph ids a composite glyph is built from (empty for simple glyphs)."""
        if len(glyph) < 10 or _i16(glyph, 0) >= 0:
            return []
        out, pos = [], 10
        while True:
            flags, gid = struct.unpack_from(">HH", glyph, pos)
            out.append(gid)
            pos += 4 + (4 if flags & 0x0001 else 2)
            if flags & 0x0008:
                pos += 2
            elif flags & 0x0040:
                pos += 4
            elif flags & 0x0080:
                pos += 8
            if not flags & 0x0020:
                return out

    def subset(self, glyph_ids):
        """Return a TrueType file holding only `glyph_ids` (plus what composites need), ids unchanged."""
        glyf = self._table("glyf")
        offsets = self._glyph_ranges()
        keep, todo = set(), [0] + sorted(glyph_ids)
        while todo:
            gid = todo.pop()
            if gid in keep or gid >= self.num_glyphs:
                continue
            keep.add(gid)
            todo.extend(self._components(bytes(glyf[offsets[gid]:offsets[gid + 1]])))

        new_glyf, new_loca = bytearray(), bytearray()
        for gid in range(self.num_glyphs):
            new_loca += struct.pack(">I", len(new_glyf))
            if gid in keep:
                new_glyf += bytes(glyf[offsets[gid]:offsets[gid + 1]])
                new_glyf += b"\0" * (-len(new_glyf) % 4)
        new_loca += struct.pack(">I", len(new_glyf))

        head = bytearray(self._table("head"))
        struct.pack_into(">h", head, 50, 1)        # loca is written in the long format
        struct.pack_into(">I", head, 8, 0)         # checkSumAdjustment, set below
        tables = {
            "glyf": bytes(new_glyf),
            "head": bytes(head),
            "hhea": bytes(self._table("hhea")),
            "hmtx": bytes(self._table("hmtx")),
            "loca": bytes(new_loca),
            "maxp": bytes(self._table("maxp")),
        }
        return _assemble(tables)


def _checksum(data):
    data = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def _assemble(tables):
    names = sorted(tables)
    # searchRange / entrySelector / rangeShift
    entry = 0
    while (1 << (entry + 1)) <= len(names):
        entry += 1
    search = (1 << entry) * 16
    header = struct.pack(">IHHHH", 0x00010000, len(names), search, entry, len(names) * 16 - search)
    offset = 12 + 16 * len(names)
    directory, body = b"", b""
    head_pos = None
    for name in names:
        data = tables[name]
        if name == "head":
            head_pos = offset + len(body)
        directory += struct.pack(">4sIII", name.encode(), _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    font = bytearray(header + directory + body)
    adjust = (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF
    struct.pack_into(">I", font, head_pos + 8, adjust)
    return bytes(font)
