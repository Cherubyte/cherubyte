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


# A device attachment is a manual, an invoice, a warranty — downloaded, never
# rendered inline. Keep the set small and sniff every one: the extension proves
# nothing. `kind -> (extensions, media type)`.
ATTACHMENT_TYPES: dict[str, tuple[set[str], str]] = {
    "pdf": ({".pdf"}, "application/pdf"),
    "png": ({".png"}, "image/png"),
    "jpeg": ({".jpg", ".jpeg"}, "image/jpeg"),
    "gif": ({".gif"}, "image/gif"),
    "webp": ({".webp"}, "image/webp"),
    "text": ({".txt", ".md", ".csv", ".log"}, "text/plain; charset=utf-8"),
}


def sniff_attachment(head: bytes) -> str | None:
    """The attachment kind the leading bytes describe, or None if unrecognised.

    Images reuse ``sniff_image`` (minus SVG — an SVG is a script vehicle and has
    no place as a download). A PDF starts ``%PDF-``. Anything else is only
    accepted as text, and only if it has no NUL byte and decodes as UTF-8.
    """
    if head.startswith(b"%PDF-"):
        return "pdf"
    img = sniff_image(head)
    if img in {"png", "jpeg", "gif", "webp"}:
        return img
    if b"\x00" in head:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        # A multi-byte character may be sliced by the chunk boundary; tolerate
        # a short tail but reject anything that is clearly not text.
        try:
            head[:-4].decode("utf-8")
        except UnicodeDecodeError:
            return None
    return "text"


async def save_attachment_upload(
    file: UploadFile, dest: Path, *, max_bytes: int
) -> tuple[str, int]:
    """Stream `file` to `dest`, refusing anything oversized or not an allowed
    type. Returns ``(media_type, bytes_written)``. Same guarantees as
    ``save_image_upload``: size enforced mid-write, no partial file left behind.
    """
    kind: str | None = None
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                if kind is None:
                    kind = sniff_attachment(chunk)
                    if kind is None:
                        raise HTTPException(
                            400, "Unsupported file type (PDF, image or text only)"
                        )
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        413, f"File too large (max {max_bytes // 1024} KiB)"
                    )
                out.write(chunk)
        if not written:
            raise HTTPException(400, "Empty file")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return ATTACHMENT_TYPES[kind][1], written


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
                        raise HTTPException(400, "File is not a recognised image")
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        413, f"Image too large (max {max_bytes // 1024} KiB)"
                    )
                out.write(chunk)
        if not written:
            raise HTTPException(400, "Empty file")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return fmt or "unknown"
