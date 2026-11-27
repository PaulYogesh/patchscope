import pytest
from service import retry_delay

def test_initial():
    assert retry_delay(1, 3, 20) == 3

def test_exponential():
    assert retry_delay(3, 3, 20) == 12

def test_cap():
    assert retry_delay(4, 3, 20) == 20

def test_invalid_attempt():
    with pytest.raises(ValueError):
        retry_delay(0, 3, 20)
