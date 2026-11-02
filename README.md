# Reading

Personal reading tracker for books that are planned, in progress, or finished.

**Live:** <https://reading.run24.top>

## Stack

- Python 3.14.5
- Django 6.0
- uv for dependency management
- PostgreSQL
- Docker Compose locally and on Orion
- Docker Swarm on staging and production

## Local development

Create an ignored local env file and fill in secret values:

```sh
cp .env.example .env.local
```

Set `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env.local`; do not commit those values.

Run locally behind Traefik:

```sh
make local-up
make migrate
make createsuperuser
```

Open `https://readinglocal.a007.bid`.

## Orion

Create an ignored Orion env file with `DATABASE_URL`, then start the app:

The Orion compose file also exposes the app on `http://localhost:8000` for local browser checks, alongside `readingorion.a007.bid`.

```sh
cp .env.example .env.orion
make orion-up
```

Open `https://readingorion.a007.bid`.

## Checks

```sh
uv sync
make lint
make check
make test
```

## Image security scans

The `image-scan` workflow checks the production image (`ghcr.io/nikpopesku/reading-web:latest`)
with Trivy every Monday and Thursday at 07:00 UTC and can also be run manually from GitHub Actions.
After a successful staging deployment, `reading-web:staging` is scanned only when the push changed
`Dockerfile*`, `uv.lock`, or `pyproject.toml`. Manual staging runs, new branches, and force pushes
always scan. Dependency detection runs in parallel with the build. Staging still cancels superseded
runs, so a dependency change in a cancelled run is left to the scheduled production scan.
Each production deployment scans its release tag after deployment.

Scans report fixable HIGH and CRITICAL vulnerabilities. Staging, scheduled, and manual scans fail
when findings exist. Production post-deploy findings notify without failing the scan; release
creation and release notifications do not depend on scanning. Scanner or registry failures still
fail the scan job and send a separate error notification.

Configure the repository Actions secret `SLACK_SECURITY_WEBHOOK_URL` with the security-channel
incoming webhook. Alerts include the image, finding count, up to five findings (CRITICAL first),
and a link to the run logs. Clean scans send no message. If the webhook is missing, the workflow
logs a warning and skips notification; configure it before relying on security alerts.
