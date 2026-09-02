"""Safe handling of user-supplied image uploads.

Two things the previous `shutil.copyfileobj` did not do: bound the size, and
check that the bytes are actually an image. A filename extension proves
nothing — it is chosen by whoever is uploading.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..crypto import encrypt_bytes

_CHUNK = 64 * 1024

# extension -> the sniffers that may vouch for it
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

# Every file under the uploads directory shares one label. They are one kind
# of thing in one directory, and a per-file label would have to be stored
# somewhere, which is a second thing to keep in step for no gain.
UPLOAD_AAD = "uploads"


def sniff_image(head: bytes) -> str | None:
    """The image format the leading bytes describe, or None if unrecognised."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n")[:256].lower()
    if text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in head[:1024].lower()):
        return "svg"
    return None


async def save_image_upload(file: UploadFile, dest: Path, *, max_bytes: int) -> str:
    """Read `file` into `dest`, refusing anything oversized or not an image.

    Encrypted on the way down when a key is loaded: these are photographs of
    somebody's home and the disk is ours, not theirs. With no key the bytes
    are written exactly as they arrive, which is self-hosting.

    Buffered rather than streamed, because one AES-GCM operation over the
    whole file gives a single tag — a truncated file then fails to open
    instead of decoding to a shorter picture. The buffer is bounded by the
    same `max_bytes` the old streaming version enforced, and the check still
    happens while reading, so an oversized upload is refused before it is held
    in full, let alone written. A rejected upload leaves no partial file.
    """
    fmt: str | None = None
    parts: list[bytes] = []
    written = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        if fmt is None:
            fmt = sniff_image(chunk)
            if fmt is None:
                raise HTTPException(400, "File is not a recognised image")
        written += len(chunk)
        if written > max_bytes:
            raise HTTPException(413, f"Image too large (max {max_bytes // 1024} KiB)")
        parts.append(chunk)
    if not written:
        raise HTTPException(400, "Empty file")

    try:
        dest.write_bytes(encrypt_bytes(b"".join(parts), UPLOAD_AAD))
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return fmt or "unknown"
