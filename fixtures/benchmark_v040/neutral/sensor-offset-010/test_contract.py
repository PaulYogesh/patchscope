from service import display_temperature

def test_user_visible_contract():
    assert display_temperature(20, 1.5) == 21.5
    assert display_temperature(20, -1.5) == 18.5
    assert display_temperature(20, 0) == 20.0
