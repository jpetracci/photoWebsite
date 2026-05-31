import os
from flask import Flask
from .db import init_db


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.environ.get("DATABASE", "/data/photos.db"),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", "/data/uploads"),
        THUMB_DIR=os.environ.get("THUMB_DIR", "/data/thumbs"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "changeme"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB upload limit
        HOME_RANDOM_COUNT=int(os.environ.get("HOME_RANDOM_COUNT", "12")),
    )

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["THUMB_DIR"], exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    with app.app_context():
        init_db()

    from .routes import bp
    app.register_blueprint(bp)
    return app
