"""Business logic for DutyCare. Views call these functions; they raise ServiceError for user mistakes."""
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .matching import ROLE_CODE, ROLE_NEEDED, run_allocation
from .models import PERIODS, ROLES, STAFF_ROLES, Assignment, Availability, Request, Shift, User
from .security import hash_password


class ServiceError(Exception):
    pass


def parse_date(value, default: date) -> date:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def parse_int(value, default=0, low=0, high=20) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- users

def list_users(db: Session) -> list[User]:
    return db.scalars(select(User).order_by(User.role, User.id)).all()


def save_user(db: Session, form: dict, user: User | None = None, acting: User | None = None) -> User:
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    role = form.get("role", "")
    password = form.get("password", "")
    if not name or "@" not in email:
        raise ServiceError("Name and a valid email are required")
    if role not in ROLES:
        raise ServiceError("Pick a role")
    if (user is None or password) and len(password) < 6:
        raise ServiceError("Password must be at least 6 characters")
    clash = db.scalar(select(User).where(User.email == email, User.id != (user.id if user else -1)))
    if clash:
        raise ServiceError("A user with this email already exists")
    if user is not None and acting is not None and user.id == acting.id and role != "admin":
        raise ServiceError("You cannot remove your own admin role")

    if user is None:
        user = User(password_hash="")
        db.add(user)
    user.name, user.email, user.role = name, email, role
    user.department = form.get("department", "").strip()
    user.phone = form.get("phone", "").strip()
    if password:
        user.password_hash = hash_password(password)
    db.commit()
    return user


def set_user_active(db: Session, user_id: int, active: bool, acting: User) -> User:
    user = _get(db, User, user_id, "User")
    if user.id == acting.id:
        raise ServiceError("You cannot deactivate your own account")
    user.active = active
    db.commit()
    return user


def delete_user(db: Session, user_id: int, acting: User) -> str:
    user = _get(db, User, user_id, "User")
    if user.id == acting.id:
        raise ServiceError("You cannot delete your own account")
    name = user.name
    db.delete(user)
    db.commit()
    return name


def staff_member(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.role not in STAFF_ROLES:
        raise ServiceError("Doctor or nurse not found")
    return user


# ---------------------------------------------------------------- shifts

def shifts_between(db: Session, start: date, end: date) -> list[Shift]:
    shifts = db.scalars(select(Shift).where(Shift.date >= start, Shift.date <= end)).all()
    return sorted(shifts, key=lambda s: s.sort_key)


def _shift_clash(db: Session, d: date, period: str, ward: str, exclude_id: int | None = None) -> bool:
    q = select(Shift.id).where(Shift.date == d, Shift.period == period, Shift.ward == ward)
    if exclude_id is not None:
        q = q.where(Shift.id != exclude_id)
    return db.scalar(q) is not None


def save_shift(db: Session, form: dict, shift: Shift | None = None) -> Shift:
    d = parse_date(form.get("date"), None)
    period = form.get("period")
    ward = form.get("ward", "").strip() or "General"
    if d is None or period not in PERIODS:
        raise ServiceError("Pick a date and a period")
    if _shift_clash(db, d, period, ward, shift.id if shift else None):
        raise ServiceError(f"{ward} already has a {period} shift on that date")
    if shift is None:
        shift = Shift()
        db.add(shift)
    shift.date, shift.period, shift.ward = d, period, ward
    shift.doctors_needed = parse_int(form.get("doctors_needed"), 1)
    shift.nurses_needed = parse_int(form.get("nurses_needed"), 0)
    db.commit()
    return shift


def create_shifts_bulk(db: Session, form: dict, periods: list[str]) -> int:
    start, end = parse_date(form.get("start"), None), parse_date(form.get("end"), None)
    periods = [p for p in PERIODS if p in periods]
    if start is None or end is None or end < start:
        raise ServiceError("Pick a valid date range")
    if (end - start).days > 62:
        raise ServiceError("Create at most two months of shifts at once")
    if not periods:
        raise ServiceError("Pick at least one period")
    ward = form.get("ward", "").strip() or "General"
    doctors, nurses = parse_int(form.get("doctors_needed"), 1), parse_int(form.get("nurses_needed"), 0)
    created = 0
    d = start
    while d <= end:
        for period in periods:
            if not _shift_clash(db, d, period, ward):
                db.add(Shift(date=d, period=period, ward=ward, doctors_needed=doctors, nurses_needed=nurses))
                created += 1
        d += timedelta(days=1)
    db.commit()
    return created


def delete_shift(db: Session, shift_id: int):
    db.delete(_get(db, Shift, shift_id, "Shift"))
    db.commit()


# ---------------------------------------------------------------- availability

def _needs_role(shift: Shift, role: str) -> bool:
    return (shift.doctors_needed if role == "doctor" else shift.nurses_needed) > 0


def availability_for(db: Session, user: User, start: date, end: date) -> list[dict]:
    shifts = [s for s in shifts_between(db, start, end) if _needs_role(s, user.role)]
    mine = set(db.scalars(select(Availability.shift_id).where(Availability.user_id == user.id)).all())
    return [{"shift": s, "available": s.id in mine} for s in shifts]


def availability_grid(rows: list[dict]) -> list[dict]:
    """Group rows into [{date, cells: {period: [rows]}}] for the date x period table."""
    grid = {}
    for row in rows:
        day = grid.setdefault(row["shift"].date, {p: [] for p in PERIODS})
        day[row["shift"].period].append(row)
    return [{"date": d, "cells": cells} for d, cells in grid.items()]


def save_availability(db: Session, user: User, start: date, end: date, shift_ids: list[int]) -> int:
    in_range = {s.id for s in shifts_between(db, start, end) if _needs_role(s, user.role)}
    chosen = set(shift_ids) & in_range
    db.execute(delete(Availability).where(Availability.user_id == user.id, Availability.shift_id.in_(in_range)))
    for shift_id in chosen:
        db.add(Availability(user_id=user.id, shift_id=shift_id))
    db.commit()
    return len(chosen)


# ---------------------------------------------------------------- allocation

def roster(db: Session, start: date, end: date) -> list[dict]:
    shifts = shifts_between(db, start, end)
    by_shift: dict[int, list[Assignment]] = {}
    for a in db.scalars(select(Assignment).where(Assignment.shift_id.in_([s.id for s in shifts]))).all():
        by_shift.setdefault(a.shift_id, []).append(a)
    rows = []
    for s in shifts:
        people = sorted(by_shift.get(s.id, []), key=lambda a: a.slot_label)
        rows.append({
            "shift": s,
            "doctors": [a for a in people if a.role == "doctor"],
            "nurses": [a for a in people if a.role == "nurse"],
            "filled": len(people),
            "needed": s.doctors_needed + s.nurses_needed,
        })
    return rows


def analyse(db: Session, start: date, end: date, mode: str) -> dict:
    """Run the matching on current availability without saving anything."""
    shifts = shifts_between(db, start, end)
    if not shifts:
        raise ServiceError("There are no shifts in this date range. Create shifts first.")
    staff = db.scalars(select(User).where(User.role.in_(STAFF_ROLES), User.active).order_by(User.id)).all()
    availability = set(db.execute(
        select(Availability.user_id, Availability.shift_id)
        .where(Availability.shift_id.in_([s.id for s in shifts]))
    ).tuples().all())
    result = run_allocation(
        [{"id": u.id, "name": u.name, "role": u.role} for u in staff],
        [{"id": s.id, "date": s.date, "label": s.label,
          "doctors_needed": s.doctors_needed, "nurses_needed": s.nurses_needed} for s in shifts],
        availability,
        mode,
    )
    result["summary"] = {
        "slots": sum(s.doctors_needed + s.nurses_needed for s in shifts),
        "filled": len(result["assignments"]),
        "unfilled": len(result["unfilled"]),
        "unplaced": len(result["unplaced"]),
    }
    result["layouts"] = [graph_layout(g) for g in result["graphs"]]
    return result


def run_and_save(db: Session, start: date, end: date, mode: str) -> dict:
    """Run the matching and replace the roster in this range with a fresh draft."""
    if end < start:
        raise ServiceError("End date is before start date")
    result = analyse(db, start, end, mode)
    shift_ids = [s.id for s in shifts_between(db, start, end)]
    db.execute(delete(Assignment).where(Assignment.shift_id.in_(shift_ids)))
    for a in result["assignments"]:
        db.add(Assignment(user_id=a["user_id"], shift_id=a["shift_id"], role=a["role"],
                          slot_label=a["slot_label"], published=False))
    db.commit()
    return result


def publish(db: Session, start: date, end: date) -> int:
    shift_ids = [s.id for s in shifts_between(db, start, end)]
    count = db.execute(
        update(Assignment).where(Assignment.shift_id.in_(shift_ids), Assignment.published.is_(False))
        .values(published=True)
    ).rowcount
    db.commit()
    return count


def busy_on(db: Session, user_id: int, d: date) -> bool:
    return db.scalar(
        select(Assignment.id).join(Shift).where(Assignment.user_id == user_id, Shift.date == d)
    ) is not None


def candidates(db: Session, shift: Shift, role: str) -> list[dict]:
    available = set(db.scalars(select(Availability.user_id).where(Availability.shift_id == shift.id)).all())
    in_shift = set(db.scalars(select(Assignment.user_id).where(Assignment.shift_id == shift.id)).all())
    people = db.scalars(select(User).where(User.role == role, User.active).order_by(User.name)).all()
    return [
        {"user": p, "available": p.id in available, "in_shift": p.id in in_shift,
         "busy_that_day": busy_on(db, p.id, shift.date)}
        for p in people
    ]


def _free_slot_label(db: Session, shift: Shift, role: str) -> str | None:
    taken = set(db.scalars(select(Assignment.slot_label).where(
        Assignment.shift_id == shift.id, Assignment.role == role)).all())
    for i in range(1, getattr(shift, ROLE_NEEDED[role]) + 1):
        label = f"{ROLE_CODE[role]}{i}"
        if label not in taken:
            return label
    return None


def _check_person(db: Session, shift: Shift, user_id: int, role: str) -> User:
    person = db.get(User, user_id)
    if person is None or not person.active or person.role != role:
        raise ServiceError(f"Pick an active {role} for this slot")
    if db.scalar(select(Assignment.id).where(Assignment.shift_id == shift.id, Assignment.user_id == user_id)):
        raise ServiceError(f"{person.name} is already on this shift")
    return person


def add_assignment(db: Session, shift_id: int, user_id: int, role: str) -> Assignment:
    shift = _get(db, Shift, shift_id, "Shift")
    person = _check_person(db, shift, user_id, role)
    label = _free_slot_label(db, shift, role)
    if label is None:
        raise ServiceError(f"All {role} slots on this shift are already filled")
    a = Assignment(user_id=person.id, shift_id=shift.id, role=role, slot_label=label, published=False)
    db.add(a)
    db.commit()
    return a


def change_assignment(db: Session, assignment_id: int, user_id: int) -> Assignment:
    a = _get(db, Assignment, assignment_id, "Assignment")
    if a.user_id != user_id:
        _check_person(db, a.shift, user_id, a.role)
        a.user_id = user_id
        a.status = "assigned"
        db.commit()
    return a


def remove_assignment(db: Session, assignment_id: int):
    db.delete(_get(db, Assignment, assignment_id, "Assignment"))
    db.commit()


def fill_slot(db: Session, shift: Shift, role: str, slot_label: str, published: bool) -> User | None:
    """Give a freed slot to the first available staff member of the right role who is free that day."""
    people = db.scalars(
        select(User).join(Availability, Availability.user_id == User.id)
        .where(Availability.shift_id == shift.id, User.role == role, User.active)
        .order_by(User.id)
    ).all()
    for person in people:
        if not busy_on(db, person.id, shift.date):
            db.add(Assignment(user_id=person.id, shift_id=shift.id, role=role,
                              slot_label=slot_label, published=published))
            return person
    return None


# ---------------------------------------------------------------- staff duties & requests

def duties_for(db: Session, user: User) -> list[Assignment]:
    duties = db.scalars(
        select(Assignment).where(Assignment.user_id == user.id, Assignment.published.is_(True))
    ).all()
    return sorted(duties, key=lambda a: a.shift.sort_key)


def own_duty(db: Session, user: User, assignment_id: int) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if a is None or a.user_id != user.id or not a.published:
        raise ServiceError("Duty not found")
    return a


def accept_duty(db: Session, user: User, assignment_id: int) -> Assignment:
    a = own_duty(db, user, assignment_id)
    if a.status == "issue_raised":
        raise ServiceError("You have an open request on this duty; wait for the admin's decision")
    a.status = "accepted"
    db.commit()
    return a


def create_request(db: Session, user: User, assignment_id: int | None, kind: str, message: str) -> Request:
    if kind not in ("swap", "leave", "issue"):
        raise ServiceError("Pick a request type")
    message = message.strip()
    shift_id = None
    if assignment_id is not None:
        a = own_duty(db, user, assignment_id)
        if db.scalar(select(Request.id).where(Request.assignment_id == a.id, Request.status == "open")):
            raise ServiceError("There is already an open request for this duty")
        a.status = "issue_raised"
        shift_id = a.shift_id
    elif not message:
        raise ServiceError("Please describe your request")
    r = Request(user_id=user.id, assignment_id=assignment_id, shift_id=shift_id, type=kind, message=message)
    db.add(r)
    db.commit()
    return r


def list_requests(db: Session, user: User | None = None) -> list[Request]:
    q = select(Request).order_by(Request.created_at.desc())
    if user is not None:
        q = q.where(Request.user_id == user.id)
    return db.scalars(q).all()


def get_request(db: Session, request_id: int) -> Request:
    return _get(db, Request, request_id, "Request")


def decide_request(db: Session, request_id: int, decision: str, note: str) -> str:
    r = get_request(db, request_id)
    if r.status != "open":
        raise ServiceError("This request has already been decided")
    if decision not in ("approved", "rejected"):
        raise ServiceError("Pick approve or reject")

    outcome = ""
    a = db.get(Assignment, r.assignment_id) if r.assignment_id else None
    if decision == "rejected":
        if a is not None:
            a.status = "assigned"
    elif a is not None:
        # Release the duty: the person is no longer available for it, so matching won't pick them again.
        shift, role, slot_label, published = a.shift, a.role, a.slot_label, a.published
        db.execute(delete(Availability).where(Availability.user_id == a.user_id, Availability.shift_id == shift.id))
        db.delete(a)
        db.flush()
        replacement = fill_slot(db, shift, role, slot_label, published)
        outcome = (f"Slot {slot_label} given to {replacement.name}." if replacement
                   else f"No other available {role} for this shift; slot {slot_label} is now unfilled.")

    r.status = decision
    r.admin_note = "\n".join(x for x in (note.strip(), outcome) if x)
    db.commit()
    return outcome or f"Request {decision}"


# ---------------------------------------------------------------- dashboard

def stats(db: Session) -> dict:
    counts = dict(db.execute(select(User.role, func.count()).where(User.active).group_by(User.role)).tuples().all())
    today = date.today()
    week = roster(db, today, today + timedelta(days=6))
    slots = sum(r["needed"] for r in week)
    filled = sum(r["filled"] for r in week)
    published = sum(1 for r in week for a in r["doctors"] + r["nurses"] if a.published)
    return {
        "doctors": counts.get("doctor", 0),
        "nurses": counts.get("nurse", 0),
        "shifts": len(week),
        "slots": slots,
        "filled": filled,
        "published": published,
        "coverage": round(filled * 100 / slots) if slots else 0,
        "open_requests": db.scalar(select(func.count()).select_from(Request).where(Request.status == "open")),
        "week": week,
    }


# ---------------------------------------------------------------- notifications

REQUEST_TYPE_TEXT = {"swap": "swap", "leave": "leave", "issue": "issue"}


def notifications(db: Session, user: User, limit: int = 8) -> list[dict]:
    """Items for the bell menu: what needs this user's attention right now."""
    items = []
    if user.role == "admin":
        open_requests = db.scalars(
            select(Request).where(Request.status == "open").order_by(Request.created_at.desc()).limit(limit)
        ).all()
        for r in open_requests:
            items.append({
                "title": f"{r.user.name} requested {REQUEST_TYPE_TEXT[r.type]}",
                "detail": r.shift.label if r.shift else (r.message or "General request"),
                "when": r.created_at,
                "endpoint": "admin.requests",
                "kind": "request",
            })
        return items

    today = date.today()
    pending = db.scalars(
        select(Assignment).join(Shift)
        .where(Assignment.user_id == user.id, Assignment.published.is_(True),
               Assignment.status == "assigned", Shift.date >= today)
    ).all()
    for a in sorted(pending, key=lambda a: a.shift.sort_key):
        items.append({
            "title": "New duty: please accept",
            "detail": a.shift.label,
            "when": None,
            "endpoint": "staff.duties",
            "kind": "duty",
        })
    decided = db.scalars(
        select(Request).where(Request.user_id == user.id, Request.status != "open",
                              Request.created_at >= datetime.now() - timedelta(days=14))
        .order_by(Request.created_at.desc())
    ).all()
    for r in decided:
        items.append({
            "title": f"Your {REQUEST_TYPE_TEXT[r.type]} request was {r.status}",
            "detail": r.admin_note.splitlines()[0] if r.admin_note else (r.shift.label if r.shift else ""),
            "when": r.created_at,
            "endpoint": "staff.requests",
            "kind": r.status,
        })
    return items[:limit]


# ---------------------------------------------------------------- helpers

def graph_layout(graph: dict, row=54, top=34, left_x=190, right_x=560) -> dict:
    """Coordinates for drawing the bipartite graph as SVG (staff left, slots right)."""
    rows = max(len(graph["left"]), len(graph["right"]), 1)
    offset = lambda n: (rows - n) * row / 2
    ly = {p["id"]: top + offset(len(graph["left"])) + i * row for i, p in enumerate(graph["left"])}
    ry = {s["key"]: top + offset(len(graph["right"])) + i * row for i, s in enumerate(graph["right"])}
    chosen = {(u, k) for u, k in graph["chosen"]}
    matched = {k for _, k in graph["chosen"]}
    return {
        "group": graph["group"], "role": graph["role"],
        "height": top * 2 + (rows - 1) * row, "left_x": left_x, "right_x": right_x,
        # Grey edges first so the red (chosen) ones are drawn on top.
        "edges": [{"y1": ly[u], "y2": ry[k], "chosen": False} for u, k in graph["edges"] if (u, k) not in chosen]
                 + [{"y1": ly[u], "y2": ry[k], "chosen": True} for u, k in graph["chosen"]],
        "left": [{"y": ly[p["id"]], "name": p["name"]} for p in graph["left"]],
        "right": [{"y": ry[s["key"]], "label": s["label"], "filled": s["key"] in matched} for s in graph["right"]],
    }


def _get(db: Session, model, obj_id: int, what: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise ServiceError(f"{what} not found")
    return obj
