def may_view(role, user_id, owner_id):
    """Check document access for administrators and the owner."""
    return role == "admin" and user_id == owner_id
