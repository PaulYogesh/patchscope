from service import accept_timestamp

def test_user_visible_contract():
    assert accept_timestamp(10, 20, 10) is True
    assert accept_timestamp(10, 20, 19) is True
    assert accept_timestamp(10, 20, 20) is False
