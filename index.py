"""Vercel entry point. Vercel detects index.py at the project root and routes every request to `app`."""
import sys
import traceback
from pathlib import Path

from flask import Flask
from markupsafe import escape

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app import STATIC_FOLDER, TEMPLATE_FOLDER, init_app  # noqa: E402

# Vercel's build looks for a top-level Flask instance named `app`, so create it here.
app = Flask(__name__, template_folder=TEMPLATE_FOLDER, static_folder=STATIC_FOLDER)

try:
    init_app(app)
except Exception as exc:  # show why startup failed instead of Vercel's generic 500 page
    traceback.print_exc()  # full details go to Vercel's Runtime Logs
    # Our own RuntimeErrors are setup instructions; other errors may contain connection details, so hide them.
    reason = str(exc) if isinstance(exc, RuntimeError) else f"{type(exc).__name__}. Details are in Vercel's Runtime Logs."

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def startup_error(path):
        return (
            "<h1>DutyCare could not start</h1>"
            f"<p><b>Reason:</b> {escape(reason)}</p>"
            "<p>Check Settings → Environment Variables in the Vercel project "
            "(DATABASE_URL and DUTYCARE_SECRET), then redeploy.</p>",
            500,
        )
