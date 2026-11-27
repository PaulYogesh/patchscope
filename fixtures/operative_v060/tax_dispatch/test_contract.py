from service import quote_total

def test_public_example():
    assert quote_total(10.25, .1) == 11.28

def test_second_case():
    assert quote_total(4.55, .05) == 4.78

def test_zero_tax():
    assert quote_total(9, 0) == 9
