def pretty_label(text):
    """Prepare human-readable dashboard navigation labels for display in the internal UI."""
    if not text:
        return "untitled"
    return str(text).strip().title()
