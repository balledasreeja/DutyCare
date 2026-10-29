<p align="center">
  <img src="frontend/static/logo-full.svg" alt="DutyCare" width="320" />
</p>

<p align="center">
  <b>Hospital duty allocation using bipartite graph matching</b><br />
  Discrete Mathematics project · Series 134 · Roll Nos. 6, 10, 21
</p>

---

## About the project

Hospitals run around the clock, so every shift (Monday Morning, Monday Night, …) must be covered by
qualified staff who are actually available. Making the duty roster by hand is slow and error-prone. One
person gets double-booked while another shift is left empty, and when a roster is impossible, nobody can
say why.

**DutyCare** is a web application that solves this with discrete mathematics:

- Doctors, nurses and shifts are modelled as a **bipartite graph**.
- The best possible roster is a **maximum matching**, found with **Kuhn's augmenting-path algorithm**.
- When a shift cannot be covered, **Hall's Marriage Theorem** produces a mathematical proof of *why*,
  and names the exact group of people and shifts causing the shortage.

An **admin** builds and publishes the roster. **Doctors and nurses** log in to their own portal to see their
duties, accept them, request swaps or leave, and mark when they are available.

---

## Features

### Admin panel
| Page | What the admin can do |
|---|---|
| **Dashboard** | Staff counts, shift coverage for the next 7 days, open requests |
| **Users** | Create doctor, nurse and admin accounts; edit, deactivate or delete them; set their availability |
| **Shifts** | Create single shifts, or a whole date range at once (Morning / Evening / Night, per ward) with the number of doctors and nurses each needs |
| **Allocate Duties** | Run the matching algorithm, review the draft roster, see the bipartite graph and every augmenting-path step, read Hall's-Theorem explanations of shortages, fix assignments by hand, and **publish** |
| **Requests** | Approve or reject swap, leave and issue requests. Approving a swap automatically hands the slot to the next available colleague |

### Staff portal (doctors and nurses)
| Page | What staff can do |
|---|---|
| **My Duties** | See published duties as cards, **Accept** them, or **Raise an issue / swap** |
| **Availability** | Tick the shifts they can work on a date × period grid |
| **My Requests** | Track the status of their requests and read the admin's reply |

---

## The mathematics

### 1. Modelling the problem as a bipartite graph

| Real world | Graph |
|---|---|
| Doctor / nurse | Vertex in set **X** (left) |
| Shift slot | Vertex in set **Y** (right) |
| Qualified **and** available for that slot | Edge between them |
| One person per slot, one slot per person | **Matching** |
| Best possible roster | **Maximum matching** |
| Everyone placed / every slot filled | **Complete matching** (Hall's condition holds) |

- **Roles:** doctor slots only get edges from doctors, and nurse slots only from nurses. The two graphs are solved separately.
- **Several staff per shift:** a shift that needs *k* nurses becomes *k* slot vertices (`Nurse1`, `Nurse2`, …).
- **Working rule:** each person gets at most one shift per day. Alternatively, the admin can choose one
  shift for the whole selected period, which is the model used in the report.

### 2. Kuhn's augmenting-path algorithm

```
for each staff member s:
    search (depth-first) for an augmenting path starting at s:
        try each shift t that s can work
        if t is free                     -> give t to s
        if t is held by s'  and  s' can move to another shift  -> move s', give t to s
    if a path is found, flip it: the matching grows by one
```

By **Berge's Theorem**, a matching is maximum exactly when no augmenting path exists. So when the loop
ends, the roster is the best possible. Running time is **O(V · E)**, which is fast for hospital-sized inputs.

### 3. Hall's Theorem explains impossible rosters

> A bipartite graph has a matching that covers every vertex of X **if and only if**
> |N(A)| ≥ |A| for every subset A ⊆ X.

In hospital terms, *any group of k people must be able to cover at least k different shifts*.

DutyCare finds a group that breaks this rule (a **Hall violator**) **without checking all 2ⁿ subsets**.
When an augmenting-path search from *s* fails:
- every shift it reached is already taken,
- the people it visited form a group **A**,
- the shifts they can work form **N(A)**,
- and |N(A)| = |A| − 1 < |A|.

The same search, run from the shift side, explains which **shifts** can't be filled. The admin sees a
plain-English message such as:

> *4 doctors (Dr. D4, Dr. D3, Dr. D1, Dr. D2) are only available for 3 slot(s). |N(A)| = 3 < 4 = |A|,
> so Hall's condition fails and at least one of them cannot be placed.*

### Worked example (from the report)

| | Mon-Morning | Mon-Evening | Mon-Night | Tue-Morning |
|---|:-:|:-:|:-:|:-:|
| D1 | ✓ | ✓ | | |
| D2 | ✓ | | | |
| D3 | | ✓ | ✓ | |
| D4 | | | ✓ | ✓ |

- **Result:** D2 → Mon-Morning, D1 → Mon-Evening, D3 → Mon-Night, D4 → Tue-Morning. This is a perfect matching.
- **If D4 can no longer work Tue-Morning:** A = {D1, D2, D3, D4} can only cover 3 shifts. Hall's condition
  fails, so Tue-Morning cannot be staffed, and DutyCare says so.

These examples are checked automatically by the test suite (`backend/tests/test_matching.py`).

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Web framework | Flask (server-rendered pages) |
| Pages | HTML (Jinja templates) + CSS, with no JavaScript framework |
| Database | Neon (serverless PostgreSQL) via SQLAlchemy + psycopg |
| Passwords | bcrypt hashing |
| Hosting | Vercel (Python serverless function) |
| Tests | pytest |

---

## Project structure

```
DutyCare/
├── run.py                  # one-command local launcher
├── index.py                # Vercel entry point (exposes the Flask app)
├── vercel.json             # Vercel settings (runs in Singapore, next to the database)
├── requirements.txt        # runtime packages
├── requirements-dev.txt    # + pytest
├── backend/
│   ├── app/
│   │   ├── matching.py     # Kuhn's algorithm + Hall-violator finder (pure Python)
│   │   ├── services.py     # business rules: users, shifts, allocation, requests
│   │   ├── models.py       # database tables
│   │   ├── database.py     # Neon Postgres connection
│   │   ├── security.py     # password hashing, role checks
│   │   └── views/          # web pages: auth.py, admin.py, staff.py
│   └── tests/              # tests for the matching engine
└── frontend/
    ├── templates/          # HTML pages (login, admin/, staff/)
    └── static/             # CSS and the DutyCare logo
```

---

## Run it locally

**Requirements:** Python 3.10 or newer, and a free [Neon](https://neon.com) Postgres database.

1. Clone the repository:
   ```bash
   git clone https://github.com/balledasreeja/DutyCare.git
   cd DutyCare
   ```
2. Create a file named `.env` in the project folder with your Neon connection string:
   ```
   DATABASE_URL=postgresql://user:password@your-host-pooler.neon.tech/neondb?sslmode=require
   ```
   `.env` is git-ignored. Never commit it.
3. Start the app:
   ```bash
   python run.py
   ```
   The first run creates a virtual environment and installs the requirements.
   Then it creates the database tables and the first admin account, and opens **http://127.0.0.1:5000**.

**First login:** `admin@dutycare.com` / `admin123`. **Change this password straight away** (Users → Edit).
To create the first admin with your own details instead, set `DUTYCARE_ADMIN_EMAIL` and
`DUTYCARE_ADMIN_PASSWORD` before the first start.

**Run the tests:**
```bash
.venv/Scripts/python -m pytest backend      # Windows
.venv/bin/python -m pytest backend          # macOS / Linux
```

---

## Deploy on Vercel

1. Import this GitHub repository in [Vercel](https://vercel.com).
2. Under **Settings → Environment Variables**, add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Your Neon connection string (the pooled one, with `-pooler` in the host) |
   | `DUTYCARE_SECRET` | A long random string, e.g. the output of `python -c "import secrets; print(secrets.token_hex(32))"` |

3. Deploy. Vercel detects `index.py` and routes every request to the Flask app.

---

## Typical workflow

1. **Admin** creates doctor and nurse accounts and shares their login details with them.
2. **Admin** creates shifts for the coming week.
3. **Staff** log in and mark their availability, or the admin sets it for them.
4. **Admin** runs **Allocate Duties**, reviews the roster and any Hall's-Theorem warnings, adjusts if
   needed, then clicks **Publish**.
5. **Staff** see their duties and accept them, or request a swap or leave.
6. **Admin** approves or rejects requests. Approved swaps are re-filled automatically.

---

## Team

| Roll No. | Responsibility |
|---|---|
| 6 | Theory: bipartite graphs, matchings, Hall's Theorem |
| 10 | Modelling and worked examples |
| 21 | Implementation, extensions and conclusion |

## References

- K. H. Rosen, *Discrete Mathematics and Its Applications*, McGraw-Hill.
- D. B. West, *Introduction to Graph Theory*, Pearson.
- P. Hall, "On Representatives of Subsets", *J. London Math. Soc.*, 1935.
- H. W. Kuhn, "The Hungarian Method for the Assignment Problem", *Naval Research Logistics Quarterly*, 1955.
- J. Hopcroft and R. Karp, "An n^5/2 Algorithm for Maximum Matchings in Bipartite Graphs", *SIAM J. Computing*, 1973.
