"""Encryption at rest.

The claim this code has to earn is narrow and worth stating precisely: a
person who takes the disk gets ciphertext. So the tests that matter most read
the SQLite file directly, with SQLAlchemy out of the way, and assert that the
plaintext is not in it. Everything else here protects that one property from
the ways it usually rots — a column written without its blind index, a key
that silently is not loaded, a lookup that quietly matches nothing.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import crypto, database, keyring
from app.config import settings
from app.crypto import CryptoError, blind_index
from app.models import Device, IpAddress, MacAddress, User

ALPHA_KEY = b"\x11" * 32
BETA_KEY = b"\x22" * 32


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    """Two tenants, each with its own key, as the hosted service runs them."""
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr(settings, "key_service_url", "https://keys.test")
    monkeypatch.setattr(settings, "key_service_token", "t")
    keys = {"alpha": ALPHA_KEY, "beta": BETA_KEY}

    async def key_for(tenant_id: str) -> bytes:
        return keys[tenant_id]

    monkeypatch.setattr(keyring, "key_for", key_for)
    for tid in keys:
        await database.provision_tenant(tid)
    yield keys
    keyring.forget()
    await database.dispose_tenants()


@contextlib.asynccontextmanager
async def _unencrypted(tenant: str):
    """A session with no key, whatever the key service would have said.

    `scoped_to` fetches and installs the key itself, so wrapping it in
    `using(None)` achieves nothing — it is set again on the inside. This is
    how a database written before encryption existed gets built in a test.

    Restores the one attribute by hand rather than using monkeypatch: undo()
    is not selective, and rolling back here would also roll back the fixture
    that set the tenants directory and the key source.
    """

    async def no_key(_tenant):
        return None

    original = keyring.load_for
    keyring.load_for = no_key
    try:
        async with database.scoped_to(tenant) as session:
            yield session
    finally:
        keyring.load_for = original


def _raw(tenant: str, sql: str) -> list[tuple]:
    """Read the file the way somebody with the disk would: no ORM, no key."""
    con = sqlite3.connect(database.tenant_db_path(tenant))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# -- what is actually on the disk -------------------------------------------


@pytest.mark.asyncio
async def test_the_plaintext_is_not_in_the_file(hosted):
    async with database.scoped_to("alpha") as session:
        session.add(
            Device(name="Sam's iPhone", hostname="sams-iphone", notes="bedroom, top shelf")
        )
        await session.commit()

    rows = _raw("alpha", "SELECT name, hostname, notes FROM devices")
    blob = " ".join(str(v) for row in rows for v in row)
    for secret in ("Sam's iPhone", "sams-iphone", "bedroom"):
        assert secret not in blob
    assert blob.count(crypto.PREFIX) == 3


@pytest.mark.asyncio
async def test_it_reads_back_as_what_was_written(hosted):
    async with database.scoped_to("alpha") as session:
        session.add(Device(name="Sam's iPhone", notes="bedroom"))
        await session.commit()

    async with database.scoped_to("alpha") as session:
        device = (await session.execute(select(Device))).scalars().one()
        assert device.name == "Sam's iPhone"
        assert device.notes == "bedroom"


@pytest.mark.asyncio
async def test_one_tenants_key_does_not_open_anothers_row(hosted):
    async with database.scoped_to("alpha") as session:
        session.add(Device(name="Sam's iPhone"))
        await session.commit()

    ciphertext = _raw("alpha", "SELECT name FROM devices")[0][0]

    # Beta's key against alpha's ciphertext: refused, not silently wrong.
    with keyring.using(BETA_KEY):
        with pytest.raises(CryptoError):
            crypto.decrypt(ciphertext, "devices.name")


@pytest.mark.asyncio
async def test_a_value_cannot_be_moved_between_columns(hosted):
    # The column name is authenticated, so a ciphertext lifted out of one
    # column and pasted into another fails to open rather than quietly
    # becoming somebody's device note.
    with keyring.using(ALPHA_KEY):
        ciphertext = crypto.encrypt("bedroom, top shelf", "devices.notes")
        assert crypto.decrypt(ciphertext, "devices.notes") == "bedroom, top shelf"
        with pytest.raises(CryptoError):
            crypto.decrypt(ciphertext, "users.notes")


@pytest.mark.asyncio
async def test_the_same_value_encrypts_differently_every_time(hosted):
    # A deterministic cipher would make the file a frequency table: every
    # device on the same router shares a gateway IP, and equal ciphertext
    # would say so.
    with keyring.using(ALPHA_KEY):
        assert crypto.encrypt("192.168.1.1", "ip_addresses.address") != crypto.encrypt(
            "192.168.1.1", "ip_addresses.address"
        )


# -- blind indexes ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_device_is_still_found_by_its_mac(hosted):
    from app.services.monitor import _find_device_by_mac

    async with database.scoped_to("alpha") as session:
        session.add(Device(name="Router", macs=[MacAddress(address="aa:bb:cc:dd:ee:ff")]))
        await session.commit()

    async with database.scoped_to("alpha") as session:
        found = await _find_device_by_mac(session, "aa:bb:cc:dd:ee:ff")
        assert found is not None and found.name == "Router"
        assert await _find_device_by_mac(session, "00:00:00:00:00:00") is None


@pytest.mark.asyncio
async def test_the_index_is_a_digest_and_not_the_address(hosted):
    async with database.scoped_to("alpha") as session:
        session.add(Device(name="Router", macs=[MacAddress(address="aa:bb:cc:dd:ee:ff")]))
        await session.commit()

    address, index = _raw("alpha", "SELECT address, address_bi FROM mac_addresses")[0]
    assert "aa:bb:cc" not in address
    assert "aa:bb:cc" not in index
    assert len(index) == 32


@pytest.mark.asyncio
async def test_the_same_mac_indexes_differently_in_two_tenants(hosted):
    # Otherwise every tenant's index is one lookup table over a 48-bit space,
    # which for MAC addresses is no space at all.
    for tenant in ("alpha", "beta"):
        async with database.scoped_to(tenant) as session:
            session.add(Device(name="Router", macs=[MacAddress(address="aa:bb:cc:dd:ee:ff")]))
            await session.commit()

    a = _raw("alpha", "SELECT address_bi FROM mac_addresses")[0][0]
    b = _raw("beta", "SELECT address_bi FROM mac_addresses")[0][0]
    assert a != b


@pytest.mark.asyncio
async def test_the_index_follows_the_address_however_it_is_written(hosted):
    # `update_user` assigns attributes in a loop from a payload, so there is no
    # call site where a helper could be remembered. The validator is what makes
    # that safe.
    async with database.scoped_to("alpha") as session:
        row = IpAddress(address="192.168.1.5")
        assert row.address_bi == blind_index("192.168.1.5")
        row.address = "192.168.1.6"
        assert row.address_bi == blind_index("192.168.1.6")

        user = User(name="Sam")
        user.name = "Alex"
        assert user.name_bi == blind_index("Alex")


@pytest.mark.asyncio
async def test_casing_does_not_decide_whether_two_addresses_match(hosted):
    with keyring.using(ALPHA_KEY):
        assert blind_index("AA:BB:CC:DD:EE:FF") == blind_index("aa:bb:cc:dd:ee:ff")


@pytest.mark.asyncio
async def test_two_users_cannot_share_a_name(hosted):
    # The unique constraint moved to the blind index when the column became
    # ciphertext, and it still has to hold.
    from sqlalchemy.exc import IntegrityError

    async with database.scoped_to("alpha") as session:
        session.add(User(name="Sam"))
        await session.commit()

    with pytest.raises(IntegrityError):
        async with database.scoped_to("alpha") as session:
            session.add(User(name="Sam"))
            await session.commit()


# -- self-hosted, which has no key and needs none ---------------------------


def test_without_a_key_everything_is_plain_text():
    assert crypto.current_key.get() is None
    assert crypto.encrypt("Sam's iPhone", "devices.name") == "Sam's iPhone"
    assert crypto.decrypt("Sam's iPhone", "devices.name") == "Sam's iPhone"
    # And the index is a normalised copy, so equality lookups behave exactly
    # as they did against the old plain column.
    assert blind_index("AA:BB") == "aa:bb"


def test_an_encrypted_row_read_without_a_key_raises(hosted):
    # Returning the blob would put base64 on somebody's screen and, worse,
    # write it back as plaintext on the next save.
    with keyring.using(ALPHA_KEY):
        ciphertext = crypto.encrypt("Sam's iPhone", "devices.name")
    with pytest.raises(CryptoError, match="no key is loaded"):
        crypto.decrypt(ciphertext, "devices.name")


# -- the key service --------------------------------------------------------


def test_an_unconfigured_key_service_is_self_hosting_not_an_error(monkeypatch):
    monkeypatch.setattr(settings, "key_service_url", "")
    monkeypatch.setattr(settings, "key_service_token", "")
    assert not keyring.configured()


@pytest.mark.asyncio
async def test_a_configured_service_that_fails_never_falls_back_to_plain_text(monkeypatch):
    # The dangerous failure: running without a key would read the encrypted
    # rows as opaque strings and write new ones in plain text, mixing the two
    # in a way nothing afterwards can tell apart.
    monkeypatch.setattr(settings, "key_service_url", "https://keys.test")
    monkeypatch.setattr(settings, "key_service_token", "t")
    keyring.forget()

    async def boom(_tenant):
        raise keyring.KeyServiceError("the key service did not answer")

    monkeypatch.setattr(keyring, "key_for", boom)
    with pytest.raises(keyring.KeyServiceError):
        await keyring.load_for("alpha")


@pytest.mark.asyncio
async def test_a_key_of_the_wrong_length_is_refused(monkeypatch):
    # A short key still encrypts and still looks like it worked.
    import httpx

    monkeypatch.setattr(settings, "key_service_url", "https://keys.test")
    monkeypatch.setattr(settings, "key_service_token", "t")
    keyring.forget()

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, *_a, **_k):
            return httpx.Response(200, json={"key": "c2hvcnQ"})  # "short"

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_k: _Client())
    with pytest.raises(keyring.KeyServiceError, match="wrong length"):
        await keyring.key_for("alpha")


@pytest.mark.asyncio
async def test_a_fetched_key_is_cached_rather_than_asked_for_every_request(monkeypatch):
    # Every fetch is an audit line. Twenty a second would bury the one that
    # means something.
    import httpx

    monkeypatch.setattr(settings, "key_service_url", "https://keys.test")
    monkeypatch.setattr(settings, "key_service_token", "t")
    monkeypatch.setattr(settings, "key_cache_ttl", 300)
    keyring.forget()
    calls: list[str] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, url, **_k):
            calls.append(url)
            import base64

            return httpx.Response(
                200, json={"key": base64.urlsafe_b64encode(ALPHA_KEY).decode().rstrip("=")}
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_k: _Client())
    assert await keyring.key_for("alpha") == ALPHA_KEY
    assert await keyring.key_for("alpha") == ALPHA_KEY
    assert len(calls) == 1
    keyring.forget()


# -- photographs -------------------------------------------------------------


class _Upload:
    """The two bits of UploadFile that save_image_upload actually uses."""

    def __init__(self, data: bytes):
        self._data = data
        self._sent = False

    async def read(self, _n: int = -1) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return self._data


PNG = b"\x89PNG\r\n\x1a\n" + b"the living room" * 8


@pytest.mark.asyncio
async def test_a_photograph_is_not_readable_on_disk(hosted):
    from app.api._uploads import save_image_upload
    from app.config import upload_dir
    from app.tenancy import current_tenant

    token = current_tenant.set("alpha")
    try:
        with keyring.using(ALPHA_KEY):
            dest = upload_dir(create=True) / "dev1-aaaa.png"
            assert await save_image_upload(_Upload(PNG), dest, max_bytes=1 << 20) == "png"
    finally:
        current_tenant.reset(token)

    on_disk = dest.read_bytes()
    assert not on_disk.startswith(b"\x89PNG")
    assert b"living room" not in on_disk
    assert on_disk.startswith(crypto.FILE_MAGIC)


@pytest.mark.asyncio
async def test_the_photograph_comes_back_whole(hosted):
    with keyring.using(ALPHA_KEY):
        blob = crypto.encrypt_bytes(PNG, "uploads")
        assert crypto.decrypt_bytes(blob, "uploads") == PNG


@pytest.mark.asyncio
async def test_a_truncated_photograph_fails_rather_than_decoding_short(hosted):
    # One tag over the whole file, so a file cut in half does not quietly
    # become half a picture.
    with keyring.using(ALPHA_KEY):
        blob = crypto.encrypt_bytes(PNG, "uploads")
        with pytest.raises(CryptoError):
            crypto.decrypt_bytes(blob[: len(blob) // 2], "uploads")


@pytest.mark.asyncio
async def test_another_tenants_key_will_not_open_the_photograph(hosted):
    with keyring.using(ALPHA_KEY):
        blob = crypto.encrypt_bytes(PNG, "uploads")
    with keyring.using(BETA_KEY):
        with pytest.raises(CryptoError):
            crypto.decrypt_bytes(blob, "uploads")


@pytest.mark.asyncio
async def test_serving_decrypts_and_a_plain_file_still_works(hosted):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.config import upload_dir
    from app.main import serve_upload
    from app.tenancy import TenantMiddleware, current_tenant

    token = current_tenant.set("alpha")
    try:
        with keyring.using(ALPHA_KEY):
            d = upload_dir(create=True)
            (d / "secret.png").write_bytes(crypto.encrypt_bytes(PNG, "uploads"))
            # Written before encryption existed, or self-hosted: no magic, and
            # it has to keep working from the same directory.
            (d / "plain.png").write_bytes(PNG)
    finally:
        current_tenant.reset(token)

    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.get("/uploads/{name:path}")(serve_upload)
    headers = {settings.tenant_header: "alpha"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://panel") as c:
        with keyring.using(ALPHA_KEY):
            enc = await c.get("/uploads/secret.png", headers=headers)
            plain = await c.get("/uploads/plain.png", headers=headers)

    assert enc.status_code == 200
    assert enc.content == PNG
    assert enc.headers["content-type"] == "image/png"
    assert plain.status_code == 200 and plain.content == PNG


# -- turning it on for a database that already exists ------------------------


@pytest.mark.asyncio
async def test_a_plaintext_database_can_be_brought_under_a_key(hosted):
    from app.services.reencrypt import reencrypt

    # A beta tenant from before any of this: rows written with no key.
    async with _unencrypted("alpha") as session:
        session.add(Device(name="Old Phone", macs=[MacAddress(address="AA:BB:CC:DD:EE:FF")]))
        session.add(User(name="Sam"))
        await session.commit()

    assert "Old Phone" in str(_raw("alpha", "SELECT name FROM devices")[0][0])

    counts = await reencrypt("alpha", old_key=None, new_key=ALPHA_KEY)
    assert counts["devices.name"] == 1

    # Unreadable on disk now.
    assert "Old Phone" not in str(_raw("alpha", "SELECT name FROM devices")[0][0])
    # And, the part that actually breaks if this is skipped: the blind index
    # was rewritten too, so the device is still found by its MAC instead of
    # being rediscovered as new on the next scan.
    from app.services.monitor import _find_device_by_mac

    with keyring.using(ALPHA_KEY):
        async with database.scoped_to("alpha") as session:
            found = await _find_device_by_mac(session, "aa:bb:cc:dd:ee:ff")
            assert found is not None and found.name == "Old Phone"


@pytest.mark.asyncio
async def test_it_can_be_run_twice_without_harm(hosted):
    # An interrupted run has to be safe to start again.
    from app.services.reencrypt import reencrypt

    async with _unencrypted("alpha") as session:
        session.add(Device(name="Old Phone"))
        await session.commit()

    await reencrypt("alpha", old_key=None, new_key=ALPHA_KEY)
    await reencrypt("alpha", old_key=ALPHA_KEY, new_key=ALPHA_KEY)

    with keyring.using(ALPHA_KEY):
        async with database.scoped_to("alpha") as session:
            assert (await session.execute(select(Device))).scalars().one().name == "Old Phone"


@pytest.mark.asyncio
async def test_it_can_hand_the_data_back_on_the_way_out(hosted):
    # Offboarding is export then delete, and an export nobody can open is not
    # an export.
    from app.services.reencrypt import reencrypt

    async with database.scoped_to("alpha") as session:
        session.add(Device(name="Sam's iPhone"))
        await session.commit()

    await reencrypt("alpha", old_key=ALPHA_KEY, new_key=None)
    assert _raw("alpha", "SELECT name FROM devices")[0][0] == "Sam's iPhone"


def test_every_encrypted_column_is_found_from_the_models():
    # Listed by hand, a column added to a model and forgotten would stay in
    # plain text and nothing would say so.
    from app.services.reencrypt import encrypted_columns

    found = {(t, c) for t, c, _ in encrypted_columns()}
    for expected in (
        ("devices", "name"),
        ("devices", "hostname"),
        ("devices", "notes"),
        ("users", "name"),
        ("mac_addresses", "address"),
        ("ip_addresses", "address"),
        ("events", "message"),
    ):
        assert expected in found
    # And every one names itself, since the label is authenticated.
    assert all(aad for _t, _c, aad in encrypted_columns())
