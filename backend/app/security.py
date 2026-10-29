from functools import wraps

import bcrypt
from flask import g, redirect, request, url_for


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def home_endpoint(user) -> str:
    return "admin.dashboard" if user.role == "admin" else "staff.duties"


def require_roles(*roles):
    """Blueprint before_request hook: log in first, and only the given roles may enter."""
    def check():
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path))
        if g.user.role not in roles:
            return redirect(url_for(home_endpoint(g.user)))
        return None
    return check


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper
