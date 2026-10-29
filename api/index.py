"""Vercel entry point: exposes the Flask app as a serverless function."""
import sys
import traceback
from pathlib import Path

from markupsafe import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    from app import create_app

    app = create_app()
except Exception as exc:  # show why startup failed instead of Vercel's generic 500 page
    traceback.print_exc()  # full details go to Vercel's Runtime Logs
    from flask import Flask

    # Our own RuntimeErrors are setup instructions; other errors may contain connection details, so hide them.
    reason = str(exc) if isinstance(exc, RuntimeError) else f"{type(exc).__name__}. Details are in Vercel's Runtime Logs."
    app = Flask(__name__)

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
