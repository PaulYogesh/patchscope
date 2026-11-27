from service import can_open_document

def test_user_visible_contract():
    assert can_open_document("user", "alice", "alice") is True
    assert can_open_document("admin", "bob", "alice") is True
    assert can_open_document("user", "bob", "alice") is False
