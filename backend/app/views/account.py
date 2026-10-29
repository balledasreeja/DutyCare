from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import services as svc
from ..security import require_roles

bp = Blueprint("account", __name__, url_prefix="/settings")
bp.before_request(require_roles("admin", "doctor", "nurse"))


@bp.route("/", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        try:
            if request.form.get("section") == "password":
                svc.change_own_password(g.db, g.user, request.form.get("current", ""),
                                        request.form.get("new", ""), request.form.get("confirm", ""))
                flash("Password changed. Use the new password next time you log in.", "success")
            else:
                svc.update_own_profile(g.db, g.user, request.form)
                flash("Profile saved.", "success")
            return redirect(url_for("account.settings"))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("settings.html")
