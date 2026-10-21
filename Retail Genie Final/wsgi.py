"""WSGI entry point for the Retail Genie Flask application."""

from dotenv import load_dotenv

load_dotenv()

from retail_genie import create_app, socketio  # noqa: E402

app = create_app()
