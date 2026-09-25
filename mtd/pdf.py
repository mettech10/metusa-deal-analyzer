"""Multi-page PDF writer with word wrap (no third-party dependency)."""

from __future__ import annotations

from typing import Iterable

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT = 50
TITLE_Y = 800
BODY_START_Y = 776
BODY_BOTTOM_Y = 88
LINE_HEIGHT = 14
WRAP_WIDTH = 92
FOOTER_WRAP_WIDTH = 100


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def wrap_text(text: str, width: int = WRAP_WIDTH) -> list[str]:
    """Word-wrap so legal copy is never cut mid-word."""
    raw = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if not raw:
        return [""]
    words = raw.split()
    lines: list[str] = []
    current = ""
    for word in words:
        piece = word
        if not current:
            if len(piece) <= width:
                current = piece
                continue
            while len(piece) > width:
                lines.append(piece[:width])
                piece = piece[width:]
            current = piece
            continue
        candidate = f"{current} {piece}"
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        if len(piece) <= width:
            current = piece
            continue
        while len(piece) > width:
            lines.append(piece[:width])
            piece = piece[width:]
        current = piece
    if current:
        lines.append(current)
    return lines or [""]


def _tj(font_size: int, x: int, y: int, text: str) -> str:
    return f"BT /F1 {font_size} Tf {x} {y} Td ({_escape(text)}) Tj ET"


def _page_content(
    title: str,
    body_lines: list[str],
    *,
    disclaimer: str | None,
    page_number: int,
    page_count: int,
) -> str:
    cmds = [_tj(16, LEFT, TITLE_Y, title)]
    y = BODY_START_Y
    for raw in body_lines:
        cmds.append(_tj(10, LEFT, y, raw))
        y -= LINE_HEIGHT
    if disclaimer:
        fy = 72
        for line in wrap_text(disclaimer, FOOTER_WRAP_WIDTH):
            cmds.append(_tj(8, LEFT, fy, line))
            fy -= 10
    cmds.append(_tj(8, LEFT, 36, f"Page {page_number} of {page_count}"))
    return "\n".join(cmds)


def build_simple_pdf(
    title: str,
    lines: Iterable[str],
    *,
    disclaimer: str | None = None,
) -> bytes:
    """Return a valid PDF 1.4 document. Lines wrap; disclaimer repeats on every page."""
    wrapped: list[str] = []
    for raw in lines:
        if raw is None:
            continue
        text = str(raw)
        if text.strip() == "":
            wrapped.append("")
            continue
        wrapped.extend(wrap_text(text, WRAP_WIDTH))

    max_body_lines = max(1, (BODY_START_Y - BODY_BOTTOM_Y) // LINE_HEIGHT)
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in wrapped:
        if len(current) >= max_body_lines:
            chunks.append(current)
            current = []
        current.append(line)
    if current or not chunks:
        chunks.append(current)

    page_count = len(chunks)
    streams = [
        _page_content(
            title,
            chunk,
            disclaimer=disclaimer,
            page_number=i + 1,
            page_count=page_count,
        ).encode("latin-1", errors="replace")
        for i, chunk in enumerate(chunks)
    ]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_obj_nums = [3 + 2 * i for i in range(page_count)]
    font_obj = 3 + 2 * page_count
    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"))

    for i, stream in enumerate(streams):
        contents_num = page_obj_nums[i] + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Contents {contents_num} 0 R "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>"
            ).encode("ascii")
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))

    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)
