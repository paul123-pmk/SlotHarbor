import pytest
from datetime import datetime, timezone


def module():
    from slotharbor import times
    return times


def test_time_module_exists():
    import importlib.util
    assert importlib.util.find_spec("slotharbor.times") is not None


def test_nairobi_conversion():
    assert module().local_epoch("2030-01-07T09:00", "Africa/Nairobi") == int(
        datetime(2030, 1, 7, 6, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("value", ["not-a-date", "2030-01-07", "2030-01-07T09:00Z", "2030-01-07T09:00:30", "", None])
def test_reject_invalid_local_inputs(value):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        module().local_epoch(value, "UTC")


def test_missing_spring_time_rejected():
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError, match="does not exist"):
        module().local_epoch("2030-03-10T02:30", "America/New_York")


def test_repeated_autumn_time_needs_fold():
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError, match="ambiguous"):
        module().local_epoch("2030-11-03T01:30", "America/New_York")
    first = module().local_epoch("2030-11-03T01:30", "America/New_York", 0)
    second = module().local_epoch("2030-11-03T01:30", "America/New_York", 1)
    assert second - first == 3600


@pytest.mark.parametrize("fold", [-1, 2, "x", True])
def test_invalid_fold_rejected(fold):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        module().local_epoch("2030-01-07T09:00", "UTC", fold)


def test_invalid_zone_rejected():
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        module().local_epoch("2030-01-07T09:00", "Nowhere/Invalid")
