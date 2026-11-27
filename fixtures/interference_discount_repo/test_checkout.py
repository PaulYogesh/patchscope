import pytest
from checkout import final_price

def test_discount_twenty_percent():
    assert final_price(100, 20) == 80

def test_discount_none():
    assert final_price(100, 0) == 100

def test_discount_full():
    assert final_price(100, 100) == 0

def test_invalid_discount():
    with pytest.raises(ValueError):
        final_price(100, 150)
