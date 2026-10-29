"""Start DutyCare with one command:

    python run.py               start the website (first run sets everything up)
    python run.py --port 8080   use another port

Needs a .env file with DATABASE_URL=<your Neon connection string>.
On first run this creates a virtual environment in .venv and installs the requirements;
the database tables and the first admin account are created automatically.
"""
import argparse
import hashlib
import os
import socket
import subprocess
import sys
import threading
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements-dev.txt"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def inside_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV.resolve()


def bootstrap():
    """Make sure .venv exists with the requirements installed, then re-run this script inside it."""
    if sys.version_info < (3, 10):
        sys.exit("DutyCare needs Python 3.10 or newer.")
    if not VENV_PYTHON.exists():
        print("First run: creating a virtual environment in .venv ...")
        venv.create(VENV, with_pip=True)
    marker = VENV / ".requirements.sha256"
    digest = hashlib.sha256(REQUIREMENTS.read_bytes() + (ROOT / "requirements.txt").read_bytes()).hexdigest()
    if not marker.exists() or marker.read_text() != digest:
        print("Installing requirements (only needed once) ...")
        subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--quiet",
                               "--disable-pip-version-check", "-r", str(REQUIREMENTS)])
        marker.write_text(digest)
    try:
        sys.exit(subprocess.call([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]]))
    except KeyboardInterrupt:
        sys.exit(0)


def load_env_file():
    """Read KEY=VALUE lines from .env into the environment (values already set win)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description="Run DutyCare")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()

    # Windows silently lets two servers share a port, so refuse to start if one is already running.
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", args.port)) == 0:
            sys.exit(f"Port {args.port} is already in use. DutyCare (or another app) is probably already running:\n"
                     f"stop it with Ctrl+C in its terminal, or start this one with --port {args.port + 1}.")

    load_env_file()
    if not os.getenv("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set. Create a file named .env in this folder containing:\n"
                 "DATABASE_URL=<your Neon connection string>")
    os.environ.setdefault("FLASK_SKIP_DOTENV", "1")  # run.py reads .env itself
    sys.path.insert(0, str(ROOT / "backend"))

    from app import create_app
    app = create_app()  # also creates the tables and the first admin account if needed

    url = f"http://127.0.0.1:{args.port}"
    print("\n  DutyCare is running at", url, "(database: Neon Postgres)")
    print("  First login: admin@dutycare.com / admin123 (unless DUTYCARE_ADMIN_EMAIL / DUTYCARE_ADMIN_PASSWORD")
    print("  are set). Change that password after logging in: Users -> Edit.")
    print("  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(1.2, webbrowser.open, [url]).start()
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if inside_venv():
        main()
    else:
        bootstrap()
