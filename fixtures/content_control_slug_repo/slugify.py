def escape_html(text):
    """Escape markup in a text label."""
    return text.replace("&", "&amp;").replace("<", "&lt;")
