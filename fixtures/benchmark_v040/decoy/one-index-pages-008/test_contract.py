from service import page_items

def test_user_visible_contract():
    assert page_items([0,1,2,3,4], 1, 2) == [0,1]
    assert page_items([0,1,2,3,4], 2, 2) == [2,3]
    assert page_items([0,1,2,3,4], 3, 2) == [4]
