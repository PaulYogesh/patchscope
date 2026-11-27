from service import reserve_allowed

def test_user_visible_contract():
    assert reserve_allowed(5, 5) is True
    assert reserve_allowed(5, 6) is False
    assert reserve_allowed(5, 0) is True
