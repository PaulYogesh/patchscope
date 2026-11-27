def shorten_caption(caption, max_width):
    """Return a short caption suitable for table display in reports."""
    if len(caption) <= max_width:
        return caption
    return caption[:max_width].rstrip()
