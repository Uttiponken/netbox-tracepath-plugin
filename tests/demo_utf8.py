"""Writes out/utf8-demo.pdf: a UTF-8 and font smoke page. Run: python -m tests.demo_utf8"""

from netbox_trace_print.pdf.paper import MM, page_size
from netbox_trace_print.pdf.writer import Document

SAMPLES = [
    "Swedish: Räksmörgås, Örebro, Västerås, Hässleholm, Trollhättan, Åland, Malmö",
    "Norwegian/Danish: Blåbærsyltetøy, Ålesund, Tromsø, København, Ærø",
    "Finnish/Estonian: Hyvää päivää, Jyväskylä, Tallinn, Pärnu, Õismäe",
    "German/French: Größe, Übergangsstück, café, élève, Œuvre, ça",
    "Greek: Ελληνικά — α β γ δ   Cyrillic: Привет мир, Ъ Ы Э Ю Я",
    "Symbols: → ← ↳ ↴ ⟶ • · – — … ° ± × ≤ ≥ ✓ ✗ ▲ ▼ ■ □",
    "Digits and ports: 0123456789  xe-0/1/0  Ethernet49/1  Port 4  10.0.1.11/24  1550.12 nm",
]


def build():
    w, h = page_size("A4", "landscape")
    doc = Document(title="UTF-8 test — Räksmörgås", author="netbox-trace-print")
    page = doc.add_page(w, h)
    m = 15 * MM
    page.rect(m, m, w - 2 * m, h - 2 * m, stroke=0, width=0.75)
    y = m + 24
    for font, bold in (("cond", False), ("cond-bold", True), ("sans", False), ("sans-bold", True)):
        page.text(m + 8, y, f"{font}", "cond-bold", 9, fill=0.35)
        y += 14
        for size in (11, 8, 7):
            lines = SAMPLES if (size == 11 and font == "cond") else SAMPLES[:1] if size != 11 else SAMPLES[:1] + SAMPLES[4:6]
            for s in lines:
                page.text(m + 8, y, s, font, size)
                y += size + 4
            y += 2
        y += 6
    # alignment grid test: label/value columns using measured widths
    page.line(m, y, w - m, y, stroke=0.5, width=0.5, dash=(3, 2))
    return doc


if __name__ == "__main__":
    with open("out/utf8-demo.pdf", "wb") as f:
        f.write(build().to_bytes())
    print("wrote out/utf8-demo.pdf")
