def is_ascii(text):
    return all(ord(ch) < 128 for ch in text)
