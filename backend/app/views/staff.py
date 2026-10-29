from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import services as svc
from ..models import PERIODS
from ..security import require_roles

bp = Blueprint("staff", __name__, url_prefix="/portal")
bp.before_request(require_roles("doctor", "nurse"))

PERIOD_TIME = {"Morning": "07:00 – 15:00", "Evening": "15:00 – 23:00", "Night": "23:00 – 07:00"}


@bp.get("/")
def duties():
    today = date.today()
    all_duties = svc.duties_for(g.db, g.user)
    upcoming = [d for d in all_duties if d.shift.date >= today]
    past = [d for d in reversed(all_duties) if d.shift.date < today]
    pending = sum(1 for d in upcoming if d.status == "assigned")
    return render_template("staff/duties.html", upcoming=upcoming, past=past, pending=pending, times=PERIOD_TIME)


@bp.post("/duties/<int:assignment_id>/accept")
def accept(assignment_id):
    try:
        duty = svc.accept_duty(g.db, g.user, assignment_id)
        flash(f"You accepted {duty.shift.label}.", "success")
    except svc.ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("staff.duties"))


def _request_form(duty):
    if request.method == "POST":
        try:
            svc.create_request(g.db, g.user, duty.id if duty else None,
                               request.form.get("type", ""), request.form.get("message", ""))
            flash("Request sent to the admin. You'll see the decision under My Requests.", "success")
            return redirect(url_for("staff.duties" if duty else "staff.requests"))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("staff/request_form.html", duty=duty,
                           kind=request.form.get("type", "swap" if duty else "issue"),
                           message=request.form.get("message", ""))


@bp.route("/duties/<int:assignment_id>/request", methods=["GET", "POST"])
def raise_request(assignment_id):
    try:
        duty = svc.own_duty(g.db, g.user, assignment_id)
    except svc.ServiceError:
        abort(404)
    return _request_form(duty)


@bp.route("/requests/new", methods=["GET", "POST"])
def new_request():
    return _request_form(None)


@bp.get("/requests")
def requests():
    return render_template("staff/requests.html", requests=svc.list_requests(g.db, g.user))


@bp.route("/availability", methods=["GET", "POST"])
def availability():
    source = request.form if request.method == "POST" else request.args
    start = svc.parse_date(source.get("start"), date.today())
    end = max(start, svc.parse_date(source.get("end"), start + timedelta(days=13)))
    if request.method == "POST":
        n = svc.save_availability(g.db, g.user, start, end, [int(x) for x in request.form.getlist("shift_ids")])
        flash(f"Availability saved ({n} shift(s)). The admin will use it for the next allocation.", "success")
        return redirect(url_for("staff.availability", start=start, end=end))
    rows = svc.availability_for(g.db, g.user, start, end)
    return render_template("staff/availability.html", start=start, end=end, periods=PERIODS,
                           grid=svc.availability_grid(rows), selected=sum(r["available"] for r in rows))
