from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import select

from ..models import User
from ..security import home_endpoint, verify_password

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for(home_endpoint(g.user)))
    email = request.form.get("email", "").strip().lower()
    if request.method == "POST":
        user = g.db.scalar(select(User).where(User.email == email))
        if user is None or not verify_password(request.form.get("password", ""), user.password_hash):
            flash("Wrong email or password", "error")
        elif not user.active:
            flash("This account has been deactivated. Contact the administrator.", "error")
        else:
            session.clear()
            session["user_id"] = user.id
            next_url = request.args.get("next", "")
            # Only follow local paths, never another site.
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for(home_endpoint(user)))
    return render_template("login.html", email=email)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
