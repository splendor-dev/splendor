"""Shared pytest helpers."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def write_text_pdf(path: Path, lines: list[str]) -> None:
    content_lines = []
    for index, line in enumerate(lines):
        if index > 0:
            content_lines.append("0 -18 Td")
        content_lines.append(f"({_escape_pdf_text(line)}) Tj")
    content = "\n".join(["BT", "/F1 12 Tf", "72 720 Td", *content_lines, "ET", ""]).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
    ]
    data = _build_pdf(objects)
    path.write_bytes(data)
    assert PdfReader(str(path)).pages[0].extract_text()


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(objects: list[bytes]) -> bytes:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode())
        chunks.append(payload)
        chunks.append(b"\nendobj\n")

    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n".encode())
    chunks.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode())
    chunks.append(
        (
            f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return b"".join(chunks)
