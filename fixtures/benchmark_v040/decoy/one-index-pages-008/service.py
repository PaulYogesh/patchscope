"""Public integration surface for the paging subsystem."""
from pagination import page_start

def page_items(items, page, size):
    return items[page_start(page, size):page_start(page, size) + size]
