def to_slug(text):
    """Build a lowercase hyphen-separated slug."""
    return text.lower().strip().replace(" ", "-")
