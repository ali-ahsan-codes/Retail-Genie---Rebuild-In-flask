"""WSGI entry point for the Retail Genie Flask application."""

from retail_genie.config import load_retail_genie_environment

load_retail_genie_environment()

from retail_genie import create_app, socketio  # noqa: E402

app = create_app()
