def to_slug(text):
    """Build a lowercase hyphen-separated slug from text."""
    return text.lower().strip().replace(" ", "-")
