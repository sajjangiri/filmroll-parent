"""Print-ready QR table cards.

Two sizes on one A4 PDF so a host can send a single file to a print shop:
four small cards per page for tables, then two larger cards per page for
the bar or the entrance.
"""

from __future__ import annotations

import io

from fpdf import FPDF

from app.services import qrcodes


class _CardPDF(FPDF):
    def header(self) -> None:  # noqa: D401 - fpdf hook
        return None

    def footer(self) -> None:
        return None


def join_cards_pdf(*, code: str, title: str, copies: int = 8) -> bytes:
    png = qrcodes.join_qr_png(code, scale=10)
    join = qrcodes.join_url(code)

    pdf = _CardPDF(orientation="P", unit="mm", format="A4")
    pdf.compress = False
    pdf.set_auto_page_break(auto=False)
    pdf.set_title(f"Filmroll · {title}")

    # Table cards: 2 x 2 on A4 (210 x 297), 10 mm outer margin.
    small = min(copies, 8)
    for index in range(small):
        if index % 4 == 0:
            pdf.add_page()
        col = index % 2
        row = (index % 4) // 2
        _draw_card(
            pdf,
            png,
            title=title,
            code=code,
            join=join,
            x=10 + col * 95,
            y=12 + row * 136,
            width=90,
            height=128,
            qr=58,
        )

    # Signage: two large cards, one above the other.
    for index in range(2):
        if index % 2 == 0:
            pdf.add_page()
        _draw_card(
            pdf,
            png,
            title=title,
            code=code,
            join=join,
            x=25,
            y=12 + index * 138,
            width=160,
            height=130,
            qr=72,
        )

    return bytes(pdf.output())


def _draw_card(
    pdf: FPDF,
    png: bytes,
    *,
    title: str,
    code: str,
    join: str,
    x: float,
    y: float,
    width: float,
    height: float,
    qr: float,
) -> None:
    pdf.set_draw_color(200, 200, 200)
    pdf.rect(x, y, width, height)

    pdf.set_xy(x + 4, y + 6)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(width - 8, 5, "FILMROLL", align="C")

    pdf.set_xy(x + 4, y + 12)
    pdf.set_font("Helvetica", size=13)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(width - 8, 8, _fit(title, 28), align="C")

    qr_x = x + (width - qr) / 2
    pdf.image(io.BytesIO(png), x=qr_x, y=y + 24, w=qr)

    pdf.set_xy(x + 4, y + 24 + qr + 4)
    pdf.set_font("Helvetica", "B", size=16)
    pdf.cell(width - 8, 8, code, align="C")

    pdf.set_xy(x + 4, y + height - 16)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(width - 8, 5, "Scan to pick up a camera. No app needed.", align="C")

    pdf.set_xy(x + 4, y + height - 10)
    pdf.set_font("Helvetica", size=7)
    pdf.cell(width - 8, 4, _fit(join, 48), align="C")


def _fit(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "."
