"""Synthetic LOB content of the documented kinds (FR-023): JPEG-like, PDF-like, XML, free text."""

from __future__ import annotations

import random


def _sized(rng: random.Random, lo: int, avg: int, hi: int) -> int:
    """Size in [lo, hi] with mean close to avg (triangular with mode chosen to hit the mean)."""
    mode = max(lo, min(hi, 3 * avg - lo - hi))
    return int(rng.triangular(lo, hi, mode))


def jpeg_like(rng: random.Random, lo: int, avg: int, hi: int) -> bytes:
    n = _sized(rng, lo, avg, hi)
    body = rng.randbytes(max(0, n - 6))
    return b"\xff\xd8\xff\xe0" + body + b"\xff\xd9"


def pdf_like(rng: random.Random, lo: int, avg: int, hi: int, title: str = "Statement") -> bytes:
    n = _sized(rng, lo, avg, hi)
    head = f"%PDF-1.7\n1 0 obj << /Title ({title}) >> endobj\n".encode()
    tail = b"\n%%EOF"
    return head + rng.randbytes(max(0, n - len(head) - len(tail))) + tail


def binary_doc(rng: random.Random, mime: str, lo: int, avg: int, hi: int) -> bytes:
    if mime == "application/pdf":
        return pdf_like(rng, lo, avg, hi, "Document")
    if mime == "image/png":
        n = _sized(rng, lo, avg, hi)
        return b"\x89PNG\r\n\x1a\n" + rng.randbytes(max(0, n - 8))
    return jpeg_like(rng, lo, avg, hi)


def target_size(rng: random.Random, lo: int, avg: int, hi: int) -> int:
    return _sized(rng, lo, avg, hi)
