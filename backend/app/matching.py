"""DutyCare allocation engine: bipartite matching with Kuhn's algorithm and Hall's Theorem.

Based on duty_allocation.py from the project report, extended with
  * role filtering (doctor slots only get edges from doctors, nurse slots from nurses),
  * several slots per shift (a shift needing k nurses becomes k slot vertices),
  * a polynomial-time Hall-violator finder (read off a failed augmenting-path search).

This module is pure Python with no database access, so it can be tested on its own.
"""
from itertools import combinations

ROLE_CODE = {"doctor": "Doc", "nurse": "Nurse"}
ROLE_NEEDED = {"doctor": "doctors_needed", "nurse": "nurses_needed"}


def kuhn(adj):
    """Maximum matching of a bipartite graph given as {left: [right, ...]}.

    Returns (match_right, steps, violators):
      match_right  {right: left} for the matched edges
      steps        one entry per left vertex, in processing order
      violators    one Hall violator (A, N(A)) per left vertex that could not be placed

    When try_assign(s) fails, every shift it saw was already taken, and the search entered the
    owner of each of those shifts and explored all of that owner's options. So
    A = {s} + owners(seen) and N(A) = seen, giving |N(A)| = |A| - 1 < |A|.
    """
    match_right = {}
    steps = []
    violators = []

    def try_assign(s, seen, visited):
        visited.append(s)
        for t in adj[s]:
            if t in seen:
                continue
            seen.add(t)
            if t not in match_right or try_assign(match_right[t], seen, visited):
                match_right[t] = s
                return True
        return False

    for s in adj:
        seen, visited = set(), []
        ok = try_assign(s, seen, visited)
        steps.append({"vertex": s, "placed": ok, "matching": {v: k for k, v in match_right.items()}})
        if not ok:
            violators.append((visited, seen))
    return match_right, steps, violators


def hall_violator(adj):
    """Brute-force Hall check from the report (exponential; only for small graphs / cross-checks)."""
    left = list(adj)
    for r in range(1, len(left) + 1):
        for group in combinations(left, r):
            neighbours = set().union(*(adj[s] for s in group))
            if len(neighbours) < len(group):
                return group, neighbours
    return None


def build_slots(shifts, role):
    """Expand each shift into one slot vertex per required person of the given role."""
    code = ROLE_CODE[role]
    slots = []
    for sh in shifts:
        needed = sh[ROLE_NEEDED[role]]
        for i in range(1, needed + 1):
            slot_label = f"{code}{i}"
            slots.append({
                "key": f"{sh['id']}:{slot_label}",
                "shift_id": sh["id"],
                "slot_label": slot_label,
                "label": f"{sh['label']} · {slot_label}",
            })
    return slots


def run_allocation(staff, shifts, availability, mode="per_day"):
    """Allocate staff to shift slots.

    staff         [{id, name, role}] in processing order
    shifts        [{id, date, label, doctors_needed, nurses_needed}] sorted by time
    availability  set of (user_id, shift_id) pairs: the person is qualified and available
    mode          "per_day"     each person gets at most one shift per day (one graph per day)
                  "whole_range" each person gets at most one shift in the whole range (report model)
    """
    if mode == "per_day":
        groups = {}
        for sh in shifts:
            groups.setdefault(sh["date"], []).append(sh)
        grouped = [(f"{d:%a %d %b}", g) for d, g in groups.items()]
    else:
        grouped = [("Whole range", shifts)]

    names = {p["id"]: p["name"] for p in staff}
    result = {
        "assignments": [], "unfilled": [], "unplaced": [],
        "staff_violators": [], "slot_violators": [], "steps": [], "graphs": [],
    }

    for group_label, group_shifts in grouped:
        for role in ("doctor", "nurse"):
            slots = build_slots(group_shifts, role)
            slot_by_key = {s["key"]: s for s in slots}
            # Staff of this role with at least one edge in this group (others are simply off duty).
            adj = {}
            for p in staff:
                if p["role"] != role:
                    continue
                edges = [s["key"] for s in slots if (p["id"], s["shift_id"]) in availability]
                if edges:
                    adj[p["id"]] = edges
            if not slots and not adj:
                continue

            match_right, steps, violators = kuhn(adj)

            # Run the same search from the shift side to explain unfilled slots.
            reverse = {s["key"]: [u for u in adj if s["key"] in adj[u]] for s in slots}
            _, _, slot_violators = kuhn(reverse)

            for key, uid in match_right.items():
                s = slot_by_key[key]
                result["assignments"].append({
                    "user_id": uid, "shift_id": s["shift_id"], "role": role,
                    "slot_key": key, "slot_label": s["slot_label"],
                })
            matched_staff = set(match_right.values())
            for s in slots:
                if s["key"] not in match_right:
                    result["unfilled"].append({**s, "role": role, "group": group_label})
            for uid in adj:
                if uid not in matched_staff:
                    result["unplaced"].append({"user_id": uid, "name": names[uid], "role": role, "group": group_label})

            for step in steps:
                result["steps"].append({
                    "group": group_label, "role": role, "staff": names[step["vertex"]], "placed": step["placed"],
                    "matching": [[names[u], slot_by_key[k]["label"]] for u, k in step["matching"].items()],
                })

            seen_groups = set()
            for group, nbrs in violators:
                if frozenset(group) in seen_groups:
                    continue
                seen_groups.add(frozenset(group))
                people = [names[u] for u in group]
                slot_labels = [slot_by_key[k]["label"] for k in slots_in_order(slots, nbrs)]
                result["staff_violators"].append({
                    "group": group_label, "role": role, "staff": people, "slots": slot_labels,
                    "message": (
                        f"{len(people)} {role}s ({', '.join(people)}) are only available for "
                        f"{len(slot_labels)} slot(s). |N(A)| = {len(slot_labels)} < {len(people)} = |A|, "
                        f"so Hall's condition fails and at least one of them cannot be placed."
                    ),
                })

            seen_groups = set()
            for group, nbrs in slot_violators:
                if frozenset(group) in seen_groups:
                    continue
                seen_groups.add(frozenset(group))
                slot_labels = [slot_by_key[k]["label"] for k in group]
                people = [names[u] for u in adj if u in nbrs]
                who = ", ".join(people) if people else "nobody"
                result["slot_violators"].append({
                    "group": group_label, "role": role, "slots": slot_labels, "staff": people,
                    "message": (
                        f"{len(slot_labels)} {role} slot(s) ({', '.join(slot_labels)}) can only be covered by "
                        f"{len(people)} available {role}(s): {who}. Ask more {role}s to mark availability."
                    ),
                })

            result["graphs"].append({
                "group": group_label, "role": role,
                "left": [{"id": u, "name": names[u]} for u in adj],
                "right": [{"key": s["key"], "label": s["label"]} for s in slots],
                "edges": [[u, k] for u, ks in adj.items() for k in ks],
                "chosen": [[u, k] for k, u in match_right.items()],
            })

    return result


def slots_in_order(slots, keys):
    return [s["key"] for s in slots if s["key"] in keys]
