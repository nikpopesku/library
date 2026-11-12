# Library

Personal library: a reading tracker for books that are planned, in progress, or finished,
and a log of movies watched. The left menu switches between Reading (default) and Movies.

**Repository:** <https://github.com/nikpopesku/library>

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

The `image-scan` workflow checks the production image (`ghcr.io/nikpopesku/library-web:latest`)
with Trivy every Monday and Thursday at 07:00 UTC and can also be run manually from GitHub Actions.
Staging and production deployments do not scan; the scheduled run is the only automatic scan.

Scans report fixable HIGH and CRITICAL vulnerabilities. Scheduled and manual scans fail when
findings exist. Scanner or registry failures still fail the scan job and send a separate error
notification.

Configure the repository Actions secret `SLACK_SECURITY_WEBHOOK_URL` with the `#security` channel's
incoming webhook. Alerts include the image, finding count, up to five findings (CRITICAL first),
and a link to the run logs. Clean scans send no message. As in `pe_backend`, a missing webhook
or failed Slack request fails the notification step instead of silently skipping delivery.
Checkout, registry, scanner, and invalid-report failures send a distinct error notification.

Run `.github/scripts/image-scan.test.sh` to check the shared scan helper and Slack payloads locally
with fixture reports and a stubbed HTTP client; these tests do not post to Slack.

## Project rename (RD-42)

The project is Library; Jira keeps the `RD` key so existing ticket links and branches stay valid.
GitHub redirects the former `nikpopesku/reading` URL, but update each clone explicitly:

```sh
git remote set-url origin git@github.com:nikpopesku/library.git
git fetch origin
```

Keep existing checkout directories and worktree paths in place. A repository rename does not
require renaming local folders. Open branches can continue using the same commit history.

Deployments use `ghcr.io/nikpopesku/library-web` and also publish the same tags under
`ghcr.io/nikpopesku/reading-web` during the transition. Keep the legacy package and tags:
older release workflows still use them. The scheduled scan defaults to the Library image and automatically falls back to the
legacy production image until the first Library production release. Explicit `image-ref`
inputs are used as supplied.

Existing Swarm stacks (`reading-staging` on Sirius, `reading` on Titan), Compose container
names, deployment directories, Traefik identifiers, volumes, secrets, database names and roles
remain stable. Renaming stacks or Compose projects implicitly selects new media/database
volumes and can create parallel routers. Their migration requires a coordinated data and
monitoring cutover rather than text replacement. Django modules (`reading`, `reading_project`)
and migration labels also remain stable. The uv project metadata is named `library`.

Public and local hostnames keep their current names until the separate domain task.

After renaming GitHub, verify the repository ID, Actions secret names, `prod` environment,
branch protection/rulesets, and package access. Run CI and dispatch the staging workflow on
the RD-42 branch before merging; confirm Sirius serves the new image. Slack release and
security webhook secrets remain attached to the same repository; their next normal runs
verify delivery without sending a synthetic release notification.
