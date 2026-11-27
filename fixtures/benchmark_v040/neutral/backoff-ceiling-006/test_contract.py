from service import next_retry_seconds

def test_user_visible_contract():
    assert next_retry_seconds(1, 0, 8) == 1
    assert next_retry_seconds(1, 2, 8) == 4
    assert next_retry_seconds(1, 6, 8) == 8
