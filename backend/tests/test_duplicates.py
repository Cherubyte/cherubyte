"""Merge suggestions for one handset hiding behind a rotating MAC.

A wrong merge is worse than a missed one, so most of these pin down when the
heuristic must stay quiet.
"""

from datetime import datetime, timedelta, timezone

from app.models import Device, MacAddress
from app.services.duplicates import find

NOW = datetime.now(timezone.utc)


def device(
    id_: int,
    *,
    model: str | None = None,
    hostname: str | None = None,
    random_mac: bool = True,
    first: int = 10,
    last: int = 9,
) -> Device:
    """`first`/`last` are days ago, so a bigger number is further in the past."""
    d = Device(
        id=id_,
        model=model,
        hostname=hostname,
        first_seen=NOW - timedelta(days=first),
        last_seen=NOW - timedelta(days=last),
    )
    d.macs = [MacAddress(address=f"aa:bb:cc:00:00:{id_:02x}", is_random=random_mac)]
    return d


def test_two_random_macs_with_the_same_model_are_suggested():
    a = device(1, model="iPhone15,2", first=10, last=9)
    b = device(2, model="iPhone15,2", first=8, last=1)
    [suggestion] = find([a, b])
    assert suggestion.target is a, "the oldest entry should absorb the others"
    assert suggestion.duplicates == [b]
    assert suggestion.confidence == "alta"


def test_overlapping_lifetimes_are_never_merged():
    """Both online at once means they are two different things."""
    a = device(1, model="iPhone15,2", first=10, last=1)
    b = device(2, model="iPhone15,2", first=8, last=0)
    assert find([a, b]) == []


def test_a_stable_mac_is_left_alone():
    a = device(1, model="iPhone15,2", random_mac=False, first=10, last=9)
    b = device(2, model="iPhone15,2", random_mac=False, first=8, last=1)
    assert find([a, b]) == []


def test_a_mix_of_stable_and_random_is_left_alone():
    a = device(1, model="iPhone15,2", random_mac=False, first=10, last=9)
    b = device(2, model="iPhone15,2", random_mac=True, first=8, last=1)
    assert find([a, b]) == []


def test_different_models_are_not_merged():
    a = device(1, model="iPhone15,2", first=10, last=9)
    b = device(2, model="SM-G991B", first=8, last=1)
    assert find([a, b]) == []


def test_sightings_far_apart_are_not_merged():
    """A year-old entry and a fresh one are not the same phone."""
    a = device(1, model="iPhone15,2", first=400, last=395)
    b = device(2, model="iPhone15,2", first=5, last=1)
    assert find([a, b]) == []


def test_hostname_matching_is_reported_as_weaker():
    a = device(1, hostname="sam-telemovel", first=10, last=9)
    b = device(2, hostname="sam-telemovel", first=8, last=1)
    [suggestion] = find([a, b])
    assert suggestion.confidence == "média"


def test_devices_with_no_identity_at_all_are_skipped():
    assert find([device(1), device(2)]) == []


def test_a_device_with_no_macs_is_skipped():
    a = device(1, model="iPhone15,2")
    a.macs = []
    assert find([a, device(2, model="iPhone15,2", first=8, last=1)]) == []


def test_three_generations_of_the_same_phone_group_together():
    a = device(1, model="iPhone15,2", first=30, last=25)
    b = device(2, model="iPhone15,2", first=20, last=15)
    c = device(3, model="iPhone15,2", first=10, last=1)
    [suggestion] = find([a, b, c])
    assert suggestion.target is a
    assert {d.id for d in suggestion.duplicates} == {2, 3}
