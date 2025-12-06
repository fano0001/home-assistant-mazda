import pytest

from custom_components.mazda_cs.sensor import _num, _pct


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, None),
        (-1, None),
        (0, 0.0),
        (50, 50.0),
        (100, 100.0),
        (101, None),
        (42.7, 42.7),
        ("bad", None),
    ],
)
def test_pct(val, expected):
    assert _pct(val) == expected


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, None),
        (0, 0.0),
        (12.34, 12.34),
        (99.1, 99.1),
        ("bad", None),
    ],
)
def test_num(val, expected):
    assert _num(val) == expected
