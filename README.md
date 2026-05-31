# Photo site

A minimal Flask photography site with tag filtering, simple admin login,
local file storage, and SQLite. Ships as a Docker image so you can deploy
to a DigitalOcean Droplet, App Platform, or anywhere else.

## Features

- Home page shows a random selection of photos
- Click tag chips to filter; toggle **any** / **all** match mode
- Photo detail page with full-size image
- Admin page (username/password) to upload photos, set title + tags,
  edit tags, and delete photos
- Auto-generated thumbnails (Pillow), respects EXIF orientation

## Run locally with Docker

```bash
# Set credentials (or edit docker-compose.yml)
export SECRET_KEY=$(openssl rand -hex 32)
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=somethingstrong

docker compose up --build
```

Open http://localhost:8000. Login at `/login`, then upload photos at `/admin`.

Photos, thumbnails, and the SQLite DB live in the `photo_data` Docker
volume (mounted at `/data` in the container), so they persist across
restarts and rebuilds.

## Run locally without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=dev DATABASE=./data/photos.db \
       UPLOAD_DIR=./data/uploads THUMB_DIR=./data/thumbs \
       ADMIN_USERNAME=admin ADMIN_PASSWORD=changeme
python wsgi.py
```

## Deploying to DigitalOcean

### Option A: Droplet (any Linux VM)

1. Create a Droplet with Docker installed (DigitalOcean's "Docker on Ubuntu"
   marketplace image is fine).
2. `git clone` this repo onto the droplet.
3. Create a `.env` file with `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
4. `docker compose up -d --build`
5. Put nginx or Caddy in front for TLS, proxying to `localhost:8000`.

### Option B: App Platform

1. Push this repo to GitHub.
2. Create a new App, pointed at the repo. App Platform will detect the
   `Dockerfile` and build it.
3. Set env vars `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
4. Attach a persistent volume mounted at `/data` so uploads survive
   redeploys (otherwise photos vanish on every deploy).

## Project layout

```
app/
  __init__.py        Flask app factory
  db.py              SQLite helpers + schema
  routes.py          All routes (public, API, auth, admin)
  templates/         Jinja2 templates
  static/style.css   Minimal dark theme
wsgi.py              Gunicorn entry point
Dockerfile
docker-compose.yml
requirements.txt
```

## License

MIT — see [LICENSE](LICENSE).

## Notes / next steps

- Auth is intentionally simple (one username/password from env vars).
  Easy to swap for Google OAuth later (Authlib + Google provider).
- Local disk storage is fine for thousands of photos. For more, switch
  to DigitalOcean Spaces by replacing the `send_from_directory` calls
  and upload step with `boto3`.
- Add pagination on `/api/photos` if your collection grows large.
