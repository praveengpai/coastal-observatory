"""Print-ready A4 sheets of QR ID stickers (3 x 8 = 24 per sheet, 70 x 37 mm labels).

    python -m tools.stickers person 1 240          # OBS-P-000001 .. OBS-P-000240
    python -m tools.stickers household CVB 1 120   # CVB-001 .. CVB-120
    python -m tools.stickers sample 1 480          # WS-000001 .. WS-000480

Writes a PDF into ./stickers/. Never reuse a number range: keep a register of what was printed.
"""
import io
import os
import sys

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

COLS, ROWS = 3, 8
LABEL_W, LABEL_H = 70 * mm, 37 * mm
TOP = (A4[1] - ROWS * LABEL_H) / 2

KINDS = {
    "person": ("Person ID - health card", lambda n, _: f"OBS-P-{n:06d}"),
    "household": ("Household ID - door or card", lambda n, site: f"{site}-{n:03d}"),
    "sample": ("Water sample bottle", lambda n, _: f"WS-{n:06d}"),
}


def qr_image(text):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
    q.add_data(text)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def make(kind, start, end, site=None, out_dir="stickers"):
    title, fmt = KINDS[kind]
    if kind == "household":
        if not site or not site.isalpha() or not 2 <= len(site) <= 4:
            raise SystemExit("Household stickers need a 2–4 letter site code, e.g. CVB.")
        site = site.upper()
        if end > 999:
            raise SystemExit("Household numbers go up to 999 per site.")
    os.makedirs(out_dir, exist_ok=True)
    codes = [fmt(n, site) for n in range(start, end + 1)]
    path = os.path.join(out_dir, f"{kind}-{codes[0]}-to-{codes[-1]}.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle(f"{title}: {codes[0]} to {codes[-1]}")
    for i, code in enumerate(codes):
        pos = i % (COLS * ROWS)
        if i and pos == 0:
            c.showPage()
        col, row = pos % COLS, pos // COLS
        x = (A4[0] - COLS * LABEL_W) / 2 + col * LABEL_W
        y = A4[1] - TOP - (row + 1) * LABEL_H
        c.setStrokeGray(0.85)
        c.rect(x, y, LABEL_W, LABEL_H)
        qr = 29 * mm
        c.drawImage(qr_image(code), x + 4 * mm, y + (LABEL_H - qr) / 2, qr, qr)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x + 36 * mm, y + LABEL_H / 2 + 2 * mm, code)
        c.setFont("Helvetica", 7)
        c.drawString(x + 36 * mm, y + LABEL_H / 2 - 4 * mm, title)
        c.drawString(x + 36 * mm, y + LABEL_H / 2 - 8 * mm, "One Health Observatory")
    c.save()
    return path, len(codes)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in KINDS:
        raise SystemExit(__doc__)
    if a[0] == "household":
        path, n = make("household", int(a[2]), int(a[3]), site=a[1])
    else:
        path, n = make(a[0], int(a[1]), int(a[2]))
    print(f"{n} stickers → {path}")
