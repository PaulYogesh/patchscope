"""Public integration surface for the access subsystem."""
from policy import may_view

def can_open_document(role, user_id, owner_id):
    return may_view(role, user_id, owner_id)
