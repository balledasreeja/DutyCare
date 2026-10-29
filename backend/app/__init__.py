import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, g, redirect, request, session, url_for
from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import User
from .security import hash_password, home_endpoint

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

# (endpoint, label, icon name from frontend/templates/icons.html)
ADMIN_LINKS = [
    ("admin.dashboard", "Dashboard", "layout-dashboard"),
    ("admin.users", "Users", "users"),
    ("admin.shifts", "Shifts", "calendar-days"),
    ("admin.allocate", "Allocate Duties", "arrow-left-right"),
    ("admin.requests", "Requests", "inbox"),
    ("account.settings", "Settings", "settings"),
]
STAFF_LINKS = [
    ("staff.duties", "My Duties", "stethoscope"),
    ("staff.availability", "Availability", "calendar-check"),
    ("staff.requests", "My Requests", "message-square"),
    ("account.settings", "Settings", "settings"),
]
# Which sidebar entry is highlighted for each page (sub-pages map to their parent).
NAV_PARENT = {
    "admin.user_form": "admin.users", "admin.user_availability": "admin.users",
    "admin.shift_form": "admin.shifts", "admin.shift_bulk": "admin.shifts",
    "admin.pick_staff": "admin.allocate", "admin.decide": "admin.requests",
    "staff.raise_request": "staff.duties", "staff.new_request": "staff.requests",
}


def _secret_key() -> str:
    if os.getenv("DUTYCARE_SECRET"):
        return os.environ["DUTYCARE_SECRET"]
    if os.getenv("VERCEL"):
        # Vercel's file system is read-only and every instance would invent its own key.
        raise RuntimeError("Set the DUTYCARE_SECRET environment variable in the Vercel project settings")
    key_file = ROOT / "backend" / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


DEFAULT_ADMIN_EMAIL = "admin@dutycare.com"
DEFAULT_ADMIN_PASSWORD = "admin123"


def ensure_admin() -> bool:
    """Create the first admin account when the database has none. Returns True if one was created.

    Its login comes from DUTYCARE_ADMIN_EMAIL / DUTYCARE_ADMIN_PASSWORD when set, otherwise the defaults
    above; change the password after the first login (Users -> Edit).
    """
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.role == "admin")) is not None:
            return False
        db.add(User(
            name="Administrator",
            email=os.getenv("DUTYCARE_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower(),
            password_hash=hash_password(os.getenv("DUTYCARE_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)),
            role="admin",
            department="Administration",
        ))
        db.commit()
        return True


TEMPLATE_FOLDER = str(FRONTEND / "templates")
STATIC_FOLDER = str(FRONTEND / "static")


def create_app() -> Flask:
    return init_app(Flask(__name__, template_folder=TEMPLATE_FOLDER, static_folder=STATIC_FOLDER))


def init_app(app: Flask) -> Flask:
    """Set up the database, pages and settings on an existing Flask app."""
    if engine is None:
        raise RuntimeError("DATABASE_URL is not set. Put your Neon connection string in .env "
                           "(locally) or in the Vercel project's Environment Variables.")
    app.secret_key = _secret_key()
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    Base.metadata.create_all(engine)
    ensure_admin()

    @app.before_request
    def open_db():
        g.db = SessionLocal()
        user_id = session.get("user_id")
        user = g.db.get(User, user_id) if user_id else None
        g.user = user if user is not None and user.active else None

    @app.teardown_request
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.context_processor
    def layout_context():
        from .services import notifications

        user = g.get("user")
        links = [] if user is None else ADMIN_LINKS if user.role == "admin" else STAFF_LINKS
        return {
            "current_user": user,
            "notifications": notifications(g.db, user) if user is not None else [],
            "nav_links": links,
            "active_nav": NAV_PARENT.get(request.endpoint, request.endpoint),
            "area": "Admin Panel" if user is not None and user.role == "admin" else "Staff Portal",
        }

    @app.template_filter("day")
    def fmt_day(d):
        return d.strftime("%a %d %b")

    @app.template_filter("when")
    def fmt_when(dt: datetime):
        return dt.strftime("%d %b, %H:%M")

    @app.template_filter("initials")
    def initials(name: str):
        for prefix in ("Dr. ", "Nurse "):
            name = name.removeprefix(prefix)
        return name[:2].upper()

    from .views import account, admin, auth, staff
    app.register_blueprint(auth.bp)
    app.register_blueprint(account.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(staff.bp)

    @app.get("/")
    def index():
        if g.user is None:
            return redirect(url_for("auth.login"))
        return redirect(url_for(home_endpoint(g.user)))

    return app
