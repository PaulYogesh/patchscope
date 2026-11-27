# access compatibility
def may_view(role, user_id, owner_id):
    return role == "admin" and user_id == owner_id
