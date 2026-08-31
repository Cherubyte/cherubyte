"""Security regressions.

Each test here starts from a request that used to work and must not.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api._uploads import save_image_upload, sniff_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>"


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """A built frontend, with a secret sitting outside it."""
    root = tmp_path / "frontend" / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>spa</html>")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "segredo.env").write_text("CHERUBYTE_TELEGRAM_BOT_TOKEN=super-secreto")
    monkeypatch.setattr(main, "_dist", root)
    return tmp_path


@pytest.fixture
def client(dist):
    return TestClient(main.app)


# ------------------------------------------------------------- path traversal

@pytest.mark.parametrize(
    "probe",
    [
        "%2e%2e/segredo.env",
        "%2e%2e/%2e%2e/segredo.env",
        "%2e%2e%2f%2e%2e%2fsegredo.env",
        "assets/%2e%2e/%2e%2e/segredo.env",
        "%2e%2e/" * 12 + "etc/hostname",
    ],
)
def test_traversal_never_escapes_the_built_frontend(client, probe):
    """`/assets/*` is a StaticFiles mount, which refuses traversal itself; every
    other path goes through our own resolver. Neither may leak."""
    response = client.get("/" + probe)
    assert "secreto" not in response.text, f"{probe} leaked a file outside dist"
    assert "CHERUBYTE_" not in response.text


def test_absolute_paths_do_not_escape_either(client):
    assert "secreto" not in client.get("//etc/hostname").text


def test_a_symlink_out_of_the_frontend_is_refused(client, dist):
    (dist / "frontend" / "dist" / "escape").symlink_to(dist / "segredo.env")
    assert "secreto" not in client.get("/escape").text


def test_real_frontend_files_are_still_served(client):
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/").text == "<html>spa</html>"


def test_unknown_routes_still_fall_back_to_the_spa(client):
    """The frontend detects a missing API endpoint by getting index.html back."""
    assert client.get("/api/does-not-exist").text == "<html>spa</html>"


# ---------------------------------------------------------------------- CORS

def test_no_cross_origin_access_by_default(client):
    response = client.get(
        "/api/health", headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in {
        k.lower() for k in response.headers
    }, "any website could read the device inventory"


def test_cors_can_still_be_opted_into():
    from app.config import Settings

    assert Settings(cors_origins="http://a.test, http://b.test").cors_origin_list == [
        "http://a.test",
        "http://b.test",
    ]
    assert Settings(cors_origins="").cors_origin_list == []


# ------------------------------------------------------------- upload limits

async def test_oversized_upload_is_refused_and_leaves_nothing_behind(tmp_path):
    from fastapi import HTTPException, UploadFile
    from io import BytesIO

    dest = tmp_path / "big.png"
    upload = UploadFile(filename="big.png", file=BytesIO(PNG + b"\x00" * 100_000))

    with pytest.raises(HTTPException) as exc:
        await save_image_upload(upload, dest, max_bytes=1024)

    assert exc.value.status_code == 413
    assert not dest.exists(), "a rejected upload must not leave a partial file"


async def test_a_file_that_is_not_an_image_is_refused(tmp_path):
    from fastapi import HTTPException, UploadFile
    from io import BytesIO

    dest = tmp_path / "evil.png"
    payload = b"<?php system($_GET['c']); ?>" + b"\x00" * 32
    upload = UploadFile(filename="evil.png", file=BytesIO(payload))

    with pytest.raises(HTTPException) as exc:
        await save_image_upload(upload, dest, max_bytes=1_000_000)

    assert exc.value.status_code == 400
    assert not dest.exists()


async def test_an_empty_upload_is_refused(tmp_path):
    from fastapi import HTTPException, UploadFile
    from io import BytesIO

    dest = tmp_path / "empty.png"
    with pytest.raises(HTTPException):
        await save_image_upload(
            UploadFile(filename="e.png", file=BytesIO(b"")), dest, max_bytes=1000
        )
    assert not dest.exists()


async def test_real_images_are_accepted(tmp_path):
    from fastapi import UploadFile
    from io import BytesIO

    for name, payload, expected in [
        ("a.png", PNG, "png"),
        ("b.jpg", JPEG, "jpeg"),
        ("c.svg", SVG, "svg"),
    ]:
        dest = tmp_path / name
        fmt = await save_image_upload(
            UploadFile(filename=name, file=BytesIO(payload)), dest, max_bytes=1_000_000
        )
        assert fmt == expected
        assert dest.read_bytes() == payload


def test_sniffer_recognises_the_formats_we_accept():
    assert sniff_image(PNG) == "png"
    assert sniff_image(JPEG) == "jpeg"
    assert sniff_image(b"GIF89a" + b"\x00" * 8) == "gif"
    assert sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert sniff_image(b"<?xml version='1.0'?><svg></svg>") == "svg"
    assert sniff_image(b"not an image at all") is None


# --------------------------------------------------------- uploaded SVG is inert

def test_uploaded_files_are_served_with_a_locked_down_policy(client):
    from app.config import UPLOAD_DIR

    (UPLOAD_DIR / "probe-logo.svg").write_bytes(SVG)
    try:
        response = client.get("/uploads/probe-logo.svg")
        assert response.status_code == 200
        csp = response.headers.get("content-security-policy", "")
        assert "sandbox" in csp, "an uploaded SVG could otherwise script our origin"
        assert "default-src 'none'" in csp
        assert response.headers.get("x-content-type-options") == "nosniff"
    finally:
        (UPLOAD_DIR / "probe-logo.svg").unlink(missing_ok=True)
