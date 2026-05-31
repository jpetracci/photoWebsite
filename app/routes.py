import os
import re
import secrets
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect, url_for, session,
    send_from_directory, jsonify, current_app, abort, flash
)
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

from .db import get_db, close_db

bp = Blueprint("main", __name__)

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
THUMB_SIZE = (600, 600)


@bp.teardown_app_request
def _teardown(exc):
    close_db()


# ---------- helpers ----------

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("main.login", next=request.path))
        return f(*a, **kw)
    return wrapper


def normalize_tag(name):
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\- ]+", "", name)
    name = re.sub(r"\s+", "-", name)
    return name


def get_or_create_tag(db, name):
    name = normalize_tag(name)
    if not name:
        return None
    row = db.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    return cur.lastrowid


def photo_tags(db, photo_id):
    rows = db.execute(
        "SELECT t.name FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id "
        "WHERE pt.photo_id = ? ORDER BY t.name", (photo_id,)
    ).fetchall()
    return [r["name"] for r in rows]


def serialize_photo(db, row, detail_query=""):
    detail = url_for("main.photo_detail", photo_id=row["id"])
    if detail_query:
        detail = f"{detail}?{detail_query}"
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "info": (row["info"] if "info" in row.keys() else "") or "",
        "thumb_url": url_for("main.thumb_file", filename=row["thumb_filename"]),
        "url": url_for("main.photo_file", filename=row["filename"]),
        "detail_url": detail,
        "tags": photo_tags(db, row["id"]),
    }


def filtered_photo_ids(db, tag_names, mode):
    """Return ordered list of photo IDs matching a tag filter (no LIMIT).

    Used for prev/next navigation on the detail page so that browsing
    stays within the user's current filter.
    """
    if not tag_names:
        rows = db.execute(
            "SELECT id FROM photos ORDER BY uploaded_at DESC, id DESC"
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(tag_names))
        if mode == "all":
            rows = db.execute(
                f"""
                SELECT p.id FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.name IN ({placeholders})
                GROUP BY p.id
                HAVING COUNT(DISTINCT t.name) = ?
                ORDER BY p.uploaded_at DESC, p.id DESC
                """,
                (*tag_names, len(tag_names)),
            ).fetchall()
        else:
            rows = db.execute(
                f"""
                SELECT DISTINCT p.id, p.uploaded_at FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.name IN ({placeholders})
                ORDER BY p.uploaded_at DESC, p.id DESC
                """,
                tag_names,
            ).fetchall()
    return [r["id"] for r in rows]


def parse_tag_filter():
    raw = request.args.get("tags", "").strip()
    mode = request.args.get("mode", "any").lower()
    if mode not in ("any", "all"):
        mode = "any"
    tag_names = [normalize_tag(t) for t in raw.split(",") if t.strip()]
    tag_names = [t for t in tag_names if t]
    return tag_names, mode


# ---------- public pages ----------

@bp.route("/")
def index():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM photos ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()
    photos = [serialize_photo(db, r) for r in rows]
    tags = [r["name"] for r in db.execute("SELECT name FROM tags ORDER BY name").fetchall()]
    return render_template("index.html", photos=photos, tags=tags)


def _build_detail_query(tag_names, mode):
    if not tag_names:
        return ""
    from urllib.parse import urlencode
    return urlencode({"tags": ",".join(tag_names), "mode": mode})


@bp.route("/api/photos")
def api_photos():
    """Filter photos by tags.

    Query params:
      tags=tag1,tag2   selected tags (comma separated)
      mode=any|all     match mode (default: any)
    """
    db = get_db()
    tag_names, mode = parse_tag_filter()
    detail_q = _build_detail_query(tag_names, mode)

    if not tag_names:
        rows = db.execute(
            "SELECT * FROM photos ORDER BY uploaded_at DESC, id DESC"
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(tag_names))
        if mode == "all":
            rows = db.execute(
                f"""
                SELECT p.* FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.name IN ({placeholders})
                GROUP BY p.id
                HAVING COUNT(DISTINCT t.name) = ?
                ORDER BY p.uploaded_at DESC
                """,
                (*tag_names, len(tag_names)),
            ).fetchall()
        else:
            rows = db.execute(
                f"""
                SELECT DISTINCT p.* FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.name IN ({placeholders})
                ORDER BY p.uploaded_at DESC
                """,
                tag_names,
            ).fetchall()

    return jsonify({"photos": [serialize_photo(db, r, detail_q) for r in rows]})


@bp.route("/photo/<int:photo_id>")
def photo_detail(photo_id):
    db = get_db()
    row = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        abort(404)

    tag_names, mode = parse_tag_filter()
    detail_q = _build_detail_query(tag_names, mode)
    ids = filtered_photo_ids(db, tag_names, mode)
    prev_id = next_id = None
    if photo_id in ids:
        i = ids.index(photo_id)
        if i > 0:
            prev_id = ids[i - 1]
        if i < len(ids) - 1:
            next_id = ids[i + 1]

    def link(pid):
        if pid is None:
            return None
        url = url_for("main.photo_detail", photo_id=pid)
        return f"{url}?{detail_q}" if detail_q else url

    return render_template(
        "photo.html",
        photo=serialize_photo(db, row, detail_q),
        prev_url=link(prev_id),
        next_url=link(next_id),
        back_url=(url_for("main.index") + (f"?{detail_q}" if detail_q else "")),
    )


@bp.route("/uploads/<path:filename>")
def photo_file(filename):
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename)


@bp.route("/thumbs/<path:filename>")
def thumb_file(filename):
    return send_from_directory(current_app.config["THUMB_DIR"], filename)


# ---------- auth ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if (u == current_app.config["ADMIN_USERNAME"]
                and p == current_app.config["ADMIN_PASSWORD"]):
            session["user"] = u
            return redirect(request.args.get("next") or url_for("main.admin"))
        flash("Invalid credentials")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.index"))


# ---------- admin ----------

@bp.route("/admin", methods=["GET"])
@login_required
def admin():
    db = get_db()
    rows = db.execute("SELECT * FROM photos ORDER BY uploaded_at DESC").fetchall()
    photos = [serialize_photo(db, r) for r in rows]
    return render_template("admin.html", photos=photos)


@bp.route("/admin/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("photos")
    files = [f for f in files if f and f.filename]
    if not files:
        flash("No file selected")
        return redirect(url_for("main.admin"))

    title = request.form.get("title", "").strip()
    info = request.form.get("info", "").strip()
    tags_raw = request.form.get("tags", "")
    # Pre-resolve tag IDs once
    tag_ids = []
    for t in tags_raw.split(","):
        tid = get_or_create_tag(get_db(), t)
        if tid:
            tag_ids.append(tid)
    get_db().commit()

    saved = 0
    skipped = []
    for file in files:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            skipped.append(f"{file.filename} (unsupported)")
            continue

        base = secure_filename(file.filename.rsplit(".", 1)[0]) or "photo"
        unique = f"{base}-{secrets.token_hex(4)}.{ext}"
        upload_path = os.path.join(current_app.config["UPLOAD_DIR"], unique)
        file.save(upload_path)

        thumb_name = f"{os.path.splitext(unique)[0]}.jpg"
        thumb_path = os.path.join(current_app.config["THUMB_DIR"], thumb_name)
        try:
            with Image.open(upload_path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail(THUMB_SIZE)
                im.save(thumb_path, "JPEG", quality=85)
        except Exception as e:
            try: os.remove(upload_path)
            except FileNotFoundError: pass
            skipped.append(f"{file.filename} ({e})")
            continue

        # If multiple files, don't reuse the same title across all of them
        per_title = title if len(files) == 1 else ""
        db = get_db()
        cur = db.execute(
            "INSERT INTO photos (filename, thumb_filename, title, info) VALUES (?, ?, ?, ?)",
            (unique, thumb_name, per_title, info if len(files) == 1 else ""),
        )
        photo_id = cur.lastrowid
        for tid in tag_ids:
            db.execute(
                "INSERT OR IGNORE INTO photo_tags (photo_id, tag_id) VALUES (?, ?)",
                (photo_id, tid),
            )
        db.commit()
        saved += 1

    msg = f"Uploaded {saved} photo(s)"
    if skipped:
        msg += f"; skipped: {', '.join(skipped)}"
    flash(msg)
    return redirect(url_for("main.admin"))


@bp.route("/admin/photo/<int:photo_id>/update", methods=["POST"])
@login_required
def update_photo(photo_id):
    db = get_db()
    row = db.execute("SELECT id FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        abort(404)

    # Only update fields that were actually submitted, so the tags-only
    # form on the admin grid keeps working unchanged.
    if "title" in request.form:
        db.execute("UPDATE photos SET title = ? WHERE id = ?",
                   (request.form.get("title", "").strip(), photo_id))
    if "info" in request.form:
        db.execute("UPDATE photos SET info = ? WHERE id = ?",
                   (request.form.get("info", "").strip(), photo_id))
    if "tags" in request.form:
        db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (photo_id,))
        for t in request.form.get("tags", "").split(","):
            tag_id = get_or_create_tag(db, t)
            if tag_id:
                db.execute(
                    "INSERT OR IGNORE INTO photo_tags (photo_id, tag_id) VALUES (?, ?)",
                    (photo_id, tag_id),
                )
    db.commit()
    nxt = request.form.get("next") or url_for("main.admin")
    return redirect(nxt)


@bp.route("/admin/photo/<int:photo_id>/delete", methods=["POST"])
@login_required
def delete_photo(photo_id):
    db = get_db()
    row = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        abort(404)
    for path in (
        os.path.join(current_app.config["UPLOAD_DIR"], row["filename"]),
        os.path.join(current_app.config["THUMB_DIR"], row["thumb_filename"]),
    ):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()
    return redirect(url_for("main.admin"))
