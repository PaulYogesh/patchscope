
import pytest
from calculator import average


def test_exact_average():
    assert average([2, 4]) == 3


def test_fractional_average():
    assert average([1, 2]) == 1.5


def test_empty_input():
    with pytest.raises(ValueError):
        average([])
