"""Root entry point for Flask CLI discovery (flask run / hermes verify)."""
from server.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=app.config.get("SERVER_HOST", "0.0.0.0"),
            port=app.config.get("SERVER_PORT", 8899),
            debug=False)
