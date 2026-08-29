"""Safe handling of user-supplied image uploads.

Two things the previous `shutil.copyfileobj` did not do: bound the size, and
check that the bytes are actually an image. A filename extension proves
nothing — it is chosen by whoever is uploading.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

_CHUNK = 64 * 1024

# extension -> the sniffers that may vouch for it
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


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
    """Stream `file` to `dest`, refusing anything oversized or not an image.

    The size is enforced while writing rather than afterwards, so a huge upload
    cannot fill the disk before being rejected. A rejected upload leaves no
    partial file behind. Returns the sniffed format.
    """
    fmt: str | None = None
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                if fmt is None:
                    fmt = sniff_image(chunk)
                    if fmt is None:
                        raise HTTPException(400, "Ficheiro não é uma imagem reconhecida")
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        413, f"Imagem demasiado grande (máx. {max_bytes // 1024} KiB)"
                    )
                out.write(chunk)
        if not written:
            raise HTTPException(400, "Ficheiro vazio")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return fmt or "unknown"
