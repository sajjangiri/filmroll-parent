"""QR codes for joining a film.

Generated here rather than by a third-party image endpoint. The join URL
identifies a specific private event, and sending every one of them to an
outside service hands over a guest list nobody agreed to share.

SVG because these end up on printed table cards, where a raster code at the
wrong size is the difference between a scan that works across a room and one
that does not.
"""

from __future__ import annotations

import io

import segno

from app.core.config import get_settings


def join_url(code: str) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/f/{code}"


def join_qr_svg(code: str, scale: int = 8) -> bytes:
    """Return an SVG QR code pointing at the guest camera for this film.

    Error correction is set high because these codes get printed, propped
    against glassware and photographed at an angle in bad light. The redundancy
    costs a little density and buys a scan that still works when the card picks
    up a smudge.
    """
    qr = segno.make(join_url(code), error="h")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=scale, border=2, dark="#000000", light="#ffffff")
    return buffer.getvalue()
