# Library

Personal library: a reading tracker for books that are planned, in progress, or finished,
and a log of movies watched. The left menu switches between Reading (default) and Movies.

**Repository:** <https://github.com/nikpopesku/library>

**Live after hostname rollout:** <https://library.run24.top> (formerly `reading.run24.top`)

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

Open `https://librarylocal.a007.bid`. The former `readinglocal.a007.bid` address redirects here.

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

Production is `library.run24.top`. Staging is `library.a007.bid` and local
development is `librarylocal.a007.bid`; their former Reading addresses redirect permanently
with paths and query strings preserved. The former production hostname redirects too.
Orion keeps its hostname. Buying an entirely new production domain remains a separate task.

After renaming GitHub, verify the repository ID, Actions secret names, `prod` environment,
branch protection/rulesets, and package access. Run CI and dispatch the staging workflow on
the RD-42 branch before merging; confirm Sirius serves the new image. Slack release and
security webhook secrets remain attached to the same repository; their next normal runs
verify delivery without sending a synthetic release notification.

### Production, staging and local hostname rollout

1. In Cloudflare, create `library.run24.top` with the same origin/proxy settings as
   `reading.run24.top`. Create `library.a007.bid` with the same origin/proxy settings as
   `reading.a007.bid`, and `librarylocal.a007.bid` with the same DNS-only local target as
   `readinglocal.a007.bid`. Keep all old records.
2. Add `library.a007.bid` to the existing staging Access application with the same policies
   and monitoring service-token access. Add it to the staging origin-auth Transform Rule.
   Copy production admin Access applications/path coverage to `library.run24.top` and
   preserve the public production pages. Preserve each old hostname's Access protection
   and origin-auth coverage too. Apply any WARP/device requirements only after confirming
   the intended access policy and maintaining monitoring service-token access.
3. Merge/deploy the Traefik PR adding the new staging and production hosts to origin protection. Run its
   certificate workflow to issue the local certificate with both Reading and Library SANs;
   pull those certificate changes into the local Traefik checkout and reload Traefik.
4. Deploy this app change after DNS, Access, origin protection and certificates are ready.
   Old HTTPS production/staging/local addresses then redirect to Library at Traefik. DNS itself does
   not redirect URLs; do not add an edge redirect that could skip Access protection.
5. Merge monitoring after both new staging and production hostnames are live. Verify old/new TLS, canonical
   URLs, path/query preservation, login and a form submission. Existing sessions may need a
   fresh login on the new hostname because cookies belong to the previous hostname.

Keep the Swarm/Compose project names, volumes and database identities unchanged. Orion's
`readingorion.a007.bid` stays outside this hostname change. Production is released only
from a user-created `v*` tag after staging passes.
