"""The allocation engine must reproduce the worked examples from the project report."""
from datetime import date

from app.matching import hall_violator, kuhn, run_allocation

MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)

DOCTORS = [{"id": i, "name": f"D{i}", "role": "doctor"} for i in (1, 2, 3, 4)]
SHIFTS = [
    {"id": 10, "date": MON, "label": "Mon-Morning", "doctors_needed": 1, "nurses_needed": 0},
    {"id": 11, "date": MON, "label": "Mon-Evening", "doctors_needed": 1, "nurses_needed": 0},
    {"id": 12, "date": MON, "label": "Mon-Night", "doctors_needed": 1, "nurses_needed": 0},
    {"id": 13, "date": TUE, "label": "Tue-Morning", "doctors_needed": 1, "nurses_needed": 0},
]
EXAMPLE_1 = {(1, 10), (1, 11), (2, 10), (3, 11), (3, 12), (4, 12), (4, 13)}
EXAMPLE_2 = EXAMPLE_1 - {(4, 13)}


def roster(result):
    return {a["user_id"]: a["shift_id"] for a in result["assignments"]}


def test_kuhn_on_report_dictionary():
    avail = {
        "D1": ["Mon-Morning", "Mon-Evening"],
        "D2": ["Mon-Morning"],
        "D3": ["Mon-Evening", "Mon-Night"],
        "D4": ["Mon-Night", "Tue-Morning"],
    }
    match, steps, violators = kuhn(avail)
    assert {v: k for k, v in match.items()} == {
        "D2": "Mon-Morning", "D1": "Mon-Evening", "D3": "Mon-Night", "D4": "Tue-Morning"}
    assert all(s["placed"] for s in steps)
    assert violators == [] and hall_violator(avail) is None

    avail["D4"] = ["Mon-Night"]
    match, _, violators = kuhn(avail)
    assert len(match) == 3
    group, nbrs = violators[0]
    assert set(group) == {"D1", "D2", "D3", "D4"}
    assert nbrs == {"Mon-Morning", "Mon-Evening", "Mon-Night"}
    brute = hall_violator(avail)
    assert set(brute[0]) == set(group) and brute[1] == nbrs


def test_example_1_whole_range_matches_report():
    result = run_allocation(DOCTORS, SHIFTS, EXAMPLE_1, mode="whole_range")
    assert roster(result) == {2: 10, 1: 11, 3: 12, 4: 13}
    assert result["unfilled"] == [] and result["staff_violators"] == [] and result["slot_violators"] == []


def test_example_1_per_day_gives_same_roster():
    result = run_allocation(DOCTORS, SHIFTS, EXAMPLE_1, mode="per_day")
    assert roster(result) == {2: 10, 1: 11, 3: 12, 4: 13}
    assert result["unfilled"] == []


def test_example_2_reports_hall_violators():
    result = run_allocation(DOCTORS, SHIFTS, EXAMPLE_2, mode="whole_range")
    assert roster(result) == {2: 10, 1: 11, 3: 12}
    assert [u["name"] for u in result["unplaced"]] == ["D4"]
    [staff_v] = result["staff_violators"]
    assert set(staff_v["staff"]) == {"D1", "D2", "D3", "D4"} and len(staff_v["slots"]) == 3
    [slot_v] = result["slot_violators"]
    assert slot_v["slots"] == ["Tue-Morning · Doc1"] and slot_v["staff"] == []


def test_extension_doctors_and_nurses_with_multiple_slots():
    staff = [
        {"id": 1, "name": "Dr. A", "role": "doctor"}, {"id": 2, "name": "Dr. B", "role": "doctor"},
        {"id": 3, "name": "N1", "role": "nurse"}, {"id": 4, "name": "N2", "role": "nurse"},
        {"id": 5, "name": "N3", "role": "nurse"}, {"id": 6, "name": "N4", "role": "nurse"},
    ]
    shifts = [
        {"id": 20, "date": WED, "label": "Day", "doctors_needed": 1, "nurses_needed": 2},
        {"id": 21, "date": WED, "label": "Night", "doctors_needed": 1, "nurses_needed": 2},
    ]
    avail = {(1, 20), (1, 21), (2, 20), (3, 20), (3, 21), (4, 20), (5, 21), (6, 21)}
    result = run_allocation(staff, shifts, avail)
    assert roster(result) == {2: 20, 1: 21, 3: 20, 4: 20, 5: 21, 6: 21}
    assert result["unfilled"] == [] and result["unplaced"] == []
    # Nobody may be put in two slots of the same shift.
    pairs = [(a["user_id"], a["shift_id"]) for a in result["assignments"]]
    assert len(pairs) == len(set(pairs))
