# Deploy on GitHub + Railway (راهنمای انتشار)

## 1) GitHub
Upload the **contents of this folder** (the folder with `app.py` at its root) to a new repository.
`.env`, `*.db` and caches are already ignored by `.gitignore`.

```sh
git init && git add . && git commit -m "Persian Game Club"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

## 2) Railway
1. New Project → Deploy from GitHub repo → choose the repo.
2. Service → **Settings → Volumes** → add a Volume, mount path `/data` (SQLite lives here; without it all users are lost on every deploy).
3. Service → **Variables**:

| Variable | Value | Required |
|---|---|---|
| `APP_ENV` | `production` | yes |
| `SECRET_KEY` | long random string (see below) | yes |
| `TRUST_PROXY` | `1` | yes |
| `DATABASE_PATH` | `/data/club.db` | yes |
| `SESSION_DAYS` | `7` | no |
| `ABANDON_AFTER_SECONDS` | `86400` | no |
| `PORT` | set automatically by Railway | do not set |

Generate `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
Never change it later, or all logins are invalidated.

4. Settings → Networking → **Generate Domain** (HTTPS is required in production because cookies are `Secure`).
5. Health check is `/api/health` (configured in `railway.json`).

## Notes
- Keep **one** replica: SQLite on a single volume does not scale horizontally. The Procfile runs 2 gunicorn workers on the same file, which is supported.
- Do not set `PORT` and do not add PostgreSQL; the app uses SQLite only.
- Backup: `python database.py --backup /data/backup-YYYYMMDD.db` (Railway shell).
- After changing files in ``, bump the cache name in `sw.js`.
