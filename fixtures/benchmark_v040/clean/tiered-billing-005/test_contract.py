from service import invoice_total

def test_user_visible_contract():
    assert invoice_total(80, 10) == 88.0
    assert invoice_total(200, 5) == 210.0
    assert invoice_total(10, 0) == 10.0
