"""Local development runner. Do not expose Flask's development server in production."""

import os

from dotenv import load_dotenv

load_dotenv()

from retail_genie import create_app, socketio  # noqa: E402

app = create_app()


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    socketio.run(
        app,
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=debug,
        # This file is explicitly the local-development runner. Keep debug
        # independently configurable; production must use a proper WSGI server.
        allow_unsafe_werkzeug=True,
    )
