from text_ops import to_slug

def test_simple():
    assert to_slug("Hello World") == "hello-world"

def test_repeated_spaces():
    assert to_slug("  Hello   World  ") == "hello-world"

def test_other_whitespace():
    assert to_slug("One\tTwo\nThree") == "one-two-three"

def test_empty():
    assert to_slug("  ") == ""
