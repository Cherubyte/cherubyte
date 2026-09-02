"""Field-level encryption for the things a customer would mind us reading.

Device names, hostnames, notes, the people they belong to, and the addresses
those devices carry. All of it is a picture of somebody's home, and on the
hosted service it sits on a disk we own.

**What this does and does not buy.** The panel needs the plaintext to do its
job, so it holds the key while it runs; anyone with root on a running box can
read memory and get it. What changes is everything short of that: a stolen
disk, a copied backup, a snapshot, a decommissioned drive and a leaked file
all yield ciphertext. And because keys are fetched from a service rather than
sat next to the data, every fetch is a line in an audit log that the operator
cannot quietly remove. Say that on the site. Never say we cannot read it.

Two shapes, because the columns are asked two different questions:

*Encrypted* columns are AES-256-GCM with a random nonce, so the same name
encrypts differently every time and the ciphertext leaks nothing but length.
That also means they cannot be compared, grouped or sorted in SQL, which is
fine here: nothing searched or ordered by them anyway, and the frontend does
its filtering client-side.

*Blind indexes* are for the two columns that must still be looked up by value,
`mac_addresses.address` and `ip_addresses.address`. Alongside the ciphertext sits an HMAC of the
normalised value under a separate key. Equality still works; nothing else
does, and the HMAC is per tenant so the same MAC in two accounts gives two
different digests. Without that last part every tenant's index would be one
rainbow table over a 48-bit space, which for MACs is no space at all.

**Plaintext passes straight through when no key is loaded.** Self-hosting has
no key service and no threat model that this addresses, so the same build runs
unencrypted there. The ciphertext prefix is what tells the two apart on the
way out, which also means an existing database keeps working while it is
migrated: rows encrypt as they are rewritten, and reads handle either.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from contextvars import ContextVar

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, Text, TypeDecorator

logger = logging.getLogger("cherubyte.crypto")

# Version the format from the first line. Rotating a key or moving to another
# cipher means reading both for a while, and a prefix is the cheapest way to
# know which one a given row is.
PREFIX = "enc1:"
NONCE_LEN = 12
KEY_LEN = 32

#: The tenant's key material, set for the duration of a request. None means
#: self-hosted, or a tenant whose key has not been fetched — either way the
#: columns behave as plain text.
current_key: ContextVar[bytes | None] = ContextVar("crypto_key", default=None)


class CryptoError(RuntimeError):
    """A value could not be decrypted."""


def _derive(key: bytes, info: bytes) -> bytes:
    """One purpose per key.

    The encryption key and the blind-index key are never the same bytes: an
    HMAC digest is published in a column that equality-matching exposes, and
    reusing the encryption key there would leak into a context it was never
    analysed for. HKDF-Expand with a distinct label, no salt needed since the
    input is already a uniform 32 bytes from the key service.
    """
    return hmac.new(key, info + b"\x01", hashlib.sha256).digest()


def enabled() -> bool:
    return current_key.get() is not None


def encrypt(value: str, aad: str) -> str:
    """Ciphertext for `value`, bound to the column it belongs in.

    `aad` names the column, so a ciphertext lifted out of `devices.notes` and
    written into `users.notes` fails to open rather than quietly moving. It is
    authenticated, not encrypted, and costs nothing to carry.
    """
    key = current_key.get()
    if key is None:
        return value

    nonce = os.urandom(NONCE_LEN)
    box = AESGCM(_derive(key, b"cherubyte:enc:v1"))
    blob = nonce + box.encrypt(nonce, value.encode("utf-8"), aad.encode("ascii"))
    return PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt(value: str, aad: str) -> str:
    """The plaintext behind `value`, or `value` itself if it is not ciphertext.

    Reading a row that predates encryption is normal during a migration, and
    is the same code path as self-hosted. Only a value that *claims* to be
    ciphertext and then will not open is an error.
    """
    if not value.startswith(PREFIX):
        return value
    key = current_key.get()
    if key is None:
        # A key is the difference between a row and a blob. Returning the
        # blob would put base64 on somebody's screen and, worse, write it
        # back as plaintext on the next save.
        raise CryptoError("this row is encrypted and no key is loaded")
    raw = base64.urlsafe_b64decode(value[len(PREFIX) :].encode("ascii"))
    box = AESGCM(_derive(key, b"cherubyte:enc:v1"))
    try:
        return box.decrypt(raw[:NONCE_LEN], raw[NONCE_LEN:], aad.encode("ascii")).decode("utf-8")
    except InvalidTag as exc:
        # Wrong tenant's key, a corrupted row, or a value moved between
        # columns. All three are worth stopping for.
        raise CryptoError(f"could not decrypt a value in {aad}") from exc


def blind_index(value: str | None) -> str | None:
    """A per-tenant HMAC of `value`, for the columns still looked up by value.

    Normalised first, because the caller's casing must not decide whether two
    equal addresses match: `AA:BB` and `aa:bb` are one MAC and have to be one
    digest. Truncated to 32 hex characters, which is 128 bits and far more
    collision resistance than a table of a few hundred addresses needs.
    """
    if value is None:
        return None
    key = current_key.get()
    if key is None:
        return value.strip().lower()
    digest = hmac.new(
        _derive(key, b"cherubyte:bi:v1"), value.strip().lower().encode("utf-8"), hashlib.sha256
    )
    return digest.hexdigest()[:32]


# -- files -------------------------------------------------------------------
#
# Device photographs are the most personal thing the panel holds — pictures of
# somebody's rooms — and they live on the same disk as everything else. The
# magic bytes let a directory hold both encrypted and plain files, which is
# what makes self-hosted and a part-migrated tenant work on one code path.
#
# One AES-GCM operation over the whole file rather than a chunked frame
# format. Uploads are already bounded by `max_upload_bytes`, so the buffer is
# bounded too, and a single tag means a truncated file fails to open instead
# of silently decoding to a shorter picture.
FILE_MAGIC = b"CBE1"


def encrypt_bytes(data: bytes, aad: str) -> bytes:
    key = current_key.get()
    if key is None:
        return data
    nonce = os.urandom(NONCE_LEN)
    box = AESGCM(_derive(key, b"cherubyte:enc:v1"))
    return FILE_MAGIC + nonce + box.encrypt(nonce, data, aad.encode("ascii"))


def decrypt_bytes(blob: bytes, aad: str) -> bytes:
    """The file's contents, or the blob itself if it was never encrypted."""
    if not blob.startswith(FILE_MAGIC):
        return blob
    key = current_key.get()
    if key is None:
        raise CryptoError("this file is encrypted and no key is loaded")
    body = blob[len(FILE_MAGIC) :]
    box = AESGCM(_derive(key, b"cherubyte:enc:v1"))
    try:
        return box.decrypt(body[:NONCE_LEN], body[NONCE_LEN:], aad.encode("ascii"))
    except InvalidTag as exc:
        raise CryptoError(f"could not decrypt a file in {aad}") from exc


class _Encrypted(TypeDecorator):
    """Encrypt on the way in, decrypt on the way out, transparently.

    A type rather than a call at every site: the panel touches these columns
    in a few dozen places and one forgotten call is a plaintext row that looks
    exactly like every other until somebody reads the disk.
    """

    cache_ok = True

    def __init__(self, *args, aad: str, **kw):
        if not aad:
            raise ValueError("every encrypted column must name itself")
        self.aad = aad
        super().__init__(*args, **kw)

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(str(value), self.aad)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value, self.aad)


class EncryptedString(_Encrypted):
    impl = String
    # Set on the concrete class, not only the base: SQLAlchemy reads it off
    # the type it instantiates, and without it every statement touching an
    # encrypted column misses the compiled-statement cache.
    cache_ok = True


class EncryptedText(_Encrypted):
    impl = Text
    cache_ok = True
