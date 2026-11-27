import pytest
from limits import clamp

def test_inside():
    assert clamp(5, 0, 10) == 5

def test_too_small():
    assert clamp(-3, 0, 10) == 0

def test_too_large():
    assert clamp(50, 0, 10) == 10

def test_reversed():
    with pytest.raises(ValueError):
        clamp(3, 5, 0)
