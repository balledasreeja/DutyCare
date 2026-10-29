from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import services as svc
from ..models import PERIODS, Shift, User
from ..security import require_roles

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.before_request(require_roles("admin"))


def date_range(source=None) -> tuple[date, date]:
    source = source or request.args
    start = svc.parse_date(source.get("start"), date.today())
    end = svc.parse_date(source.get("end"), start + timedelta(days=13))
    return start, max(start, end)


# ---------------------------------------------------------------- dashboard

@bp.get("/")
def dashboard():
    return render_template("admin/dashboard.html", stats=svc.stats(g.db))


# ---------------------------------------------------------------- users

@bp.get("/users")
def users():
    q = request.args.get("q", "").strip().lower()
    role = request.args.get("role", "all")
    rows = [
        u for u in svc.list_users(g.db)
        if (role == "all" or u.role == role)
        and (not q or any(q in v.lower() for v in (u.name, u.email, u.department)))
    ]
    return render_template("admin/users.html", users=rows, q=q, role=role)


@bp.route("/users/new", methods=["GET", "POST"], endpoint="user_form")
@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"], endpoint="user_form")
def user_form(user_id=None):
    user = g.db.get(User, user_id) if user_id else None
    if user_id and user is None:
        abort(404)
    form = request.form if request.method == "POST" else None
    if form is not None:
        try:
            saved = svc.save_user(g.db, form, user, acting=g.user)
            flash(f"{saved.name} {'updated' if user else 'created'}.", "success")
            return redirect(url_for("admin.users"))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("admin/user_form.html", user=user, form=form)


@bp.post("/users/<int:user_id>/active")
def toggle_user(user_id):
    try:
        user = svc.set_user_active(g.db, user_id, request.form.get("active") == "1", g.user)
        flash(f"{user.name} {'reactivated' if user.active else 'deactivated'}.", "success")
    except svc.ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/delete")
def delete_user(user_id):
    try:
        flash(f"{svc.delete_user(g.db, user_id, g.user)} deleted.", "success")
    except svc.ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/availability", methods=["GET", "POST"])
def user_availability(user_id):
    try:
        person = svc.staff_member(g.db, user_id)
    except svc.ServiceError:
        abort(404)
    start, end = date_range(request.form if request.method == "POST" else None)
    if request.method == "POST":
        ids = [int(x) for x in request.form.getlist("shift_ids")]
        n = svc.save_availability(g.db, person, start, end, ids)
        flash(f"Availability saved for {person.name}: {n} shift(s).", "success")
        return redirect(url_for("admin.user_availability", user_id=user_id, start=start, end=end))
    rows = svc.availability_for(g.db, person, start, end)
    return render_template("admin/user_availability.html", person=person, start=start, end=end,
                           grid=svc.availability_grid(rows), periods=PERIODS)


# ---------------------------------------------------------------- shifts

@bp.get("/shifts")
def shifts():
    start, end = date_range()
    return render_template("admin/shifts.html", shifts=svc.shifts_between(g.db, start, end), start=start, end=end)


@bp.route("/shifts/new", methods=["GET", "POST"], endpoint="shift_form")
@bp.route("/shifts/<int:shift_id>/edit", methods=["GET", "POST"], endpoint="shift_form")
def shift_form(shift_id=None):
    shift = g.db.get(Shift, shift_id) if shift_id else None
    if shift_id and shift is None:
        abort(404)
    form = request.form if request.method == "POST" else None
    if form is not None:
        try:
            saved = svc.save_shift(g.db, form, shift)
            flash(f"Shift {'updated' if shift else 'created'}: {saved.label}", "success")
            return redirect(url_for("admin.shifts", start=saved.date, end=saved.date + timedelta(days=13)))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("admin/shift_form.html", shift=shift, form=form, periods=PERIODS, today=date.today())


@bp.route("/shifts/bulk", methods=["GET", "POST"])
def shift_bulk():
    form = request.form if request.method == "POST" else None
    if form is not None:
        try:
            n = svc.create_shifts_bulk(g.db, form, form.getlist("periods"))
            flash(f"{n} shift(s) created (shifts that already existed were skipped).", "success")
            return redirect(url_for("admin.shifts", start=form["start"], end=form["end"]))
        except svc.ServiceError as e:
            flash(str(e), "error")
    return render_template("admin/shift_bulk.html", form=form, periods=PERIODS,
                           today=date.today(), week=date.today() + timedelta(days=6))


@bp.post("/shifts/<int:shift_id>/delete")
def delete_shift(shift_id):
    try:
        svc.delete_shift(g.db, shift_id)
        flash("Shift deleted.", "success")
    except svc.ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.shifts", start=request.form.get("start"), end=request.form.get("end")))


# ---------------------------------------------------------------- allocation

def _allocate_args(source):
    start, end = date_range(source)
    mode = source.get("mode", "per_day")
    return {"start": start, "end": end, "mode": mode if mode in ("per_day", "whole_range") else "per_day"}


@bp.get("/allocate")
def allocate():
    args = _allocate_args(request.args)
    result = None
    if request.args.get("ran"):
        try:
            result = svc.analyse(g.db, args["start"], args["end"], args["mode"])
        except svc.ServiceError as e:
            flash(str(e), "error")
    roster = svc.roster(g.db, args["start"], args["end"])
    all_assignments = [a for r in roster for a in r["doctors"] + r["nurses"]]
    return render_template(
        "admin/allocate.html", **args, result=result, roster=roster,
        drafts=sum(1 for a in all_assignments if not a.published),
        has_published=any(a.published for a in all_assignments),
    )


@bp.post("/allocate/run")
def allocate_run():
    args = _allocate_args(request.form)
    try:
        svc.run_and_save(g.db, args["start"], args["end"], args["mode"])
        return redirect(url_for("admin.allocate", **args, ran=1))
    except svc.ServiceError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.allocate", **args))


@bp.post("/allocate/publish")
def allocate_publish():
    args = _allocate_args(request.form)
    n = svc.publish(g.db, args["start"], args["end"])
    flash(f"{n} duty assignment(s) published. Staff can now see them in their portals.", "success")
    return redirect(url_for("admin.allocate", **args))


@bp.route("/allocate/pick", methods=["GET", "POST"])
def pick_staff():
    source = request.form if request.method == "POST" else request.args
    args = _allocate_args(source)
    shift = g.db.get(Shift, source.get("shift_id", type=int) or 0)
    role = source.get("role")
    assignment_id = source.get("assignment_id", type=int)
    if shift is None or role not in ("doctor", "nurse"):
        abort(404)
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        try:
            if user_id is None:
                raise svc.ServiceError("Pick a person")
            if assignment_id:
                svc.change_assignment(g.db, assignment_id, user_id)
            else:
                svc.add_assignment(g.db, shift.id, user_id, role)
            flash("Roster updated.", "success")
            return redirect(url_for("admin.allocate", **args))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("admin/pick.html", shift=shift, role=role, assignment_id=assignment_id,
                           people=svc.candidates(g.db, shift, role), **args)


@bp.post("/assignments/<int:assignment_id>/delete")
def remove_assignment(assignment_id):
    try:
        svc.remove_assignment(g.db, assignment_id)
        flash("Removed from the roster.", "success")
    except svc.ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.allocate", **_allocate_args(request.form)))


# ---------------------------------------------------------------- requests

@bp.get("/requests")
def requests():
    status = request.args.get("status", "open")
    rows = svc.list_requests(g.db)
    open_count = sum(1 for r in rows if r.status == "open")
    shown = [r for r in rows if status == "all" or r.status == status]
    return render_template("admin/requests.html", requests=shown, status=status, open_count=open_count)


@bp.route("/requests/<int:request_id>/decide", methods=["GET", "POST"])
def decide(request_id):
    try:
        req = svc.get_request(g.db, request_id)
    except svc.ServiceError:
        abort(404)
    decision = request.values.get("decision", "approved")
    if request.method == "POST":
        try:
            flash(svc.decide_request(g.db, request_id, decision, request.form.get("note", "")), "success")
            return redirect(url_for("admin.requests"))
        except svc.ServiceError as e:
            g.db.rollback()
            flash(str(e), "error")
    return render_template("admin/decide.html", req=req, decision=decision)
