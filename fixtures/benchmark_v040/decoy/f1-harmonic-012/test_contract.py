from service import report_f1

def test_user_visible_contract():
    assert report_f1(0.5, 1.0) == 2/3
    assert report_f1(0.0, 0.0) == 0.0
    assert report_f1(1.0, 1.0) == 1.0
