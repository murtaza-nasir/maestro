import contextvars
from typing import Optional
from database.models import User

# Create a context variable to store the current user
current_user_var: contextvars.ContextVar[Optional[User]] = contextvars.ContextVar("current_user", default=None)

def set_current_user(user: Optional[User]):
    """Set the current user in the context variable"""
    current_user_var.set(user)

def get_current_user() -> Optional[User]:
    """Get the current user from the context variable"""
    return current_user_var.get()

def get_user_settings() -> Optional[dict]:
    """Get the current user's settings"""
    user = get_current_user()
    if user and user.settings:
        return user.settings
    return None
