# Library — project context

## Stack
- Django 6.x, Python 3.14, PostgreSQL, Gunicorn, WhiteNoise
- uv for dependency management (no pip/poetry)
- Ruff for linting (line-length 100) and formatting
- Coverage for test coverage

## Common commands
```
make test        # uv run python manage.py test
make lint        # uv run ruff check .
make format      # uv run ruff format .
make check       # uv run python manage.py check
make migrate     # docker compose exec web python manage.py migrate
make shell       # docker compose exec web sh
make local-up    # docker compose up -d --build
make local-down  # docker compose down
uv sync          # install dependencies (also fetches Python 3.14 if missing)
```

Always run `make lint` and `make test` before committing. If `uv` isn't on PATH, install it with
`curl -LsSf https://astral.sh/uv/install.sh | sh` and add `~/.local/bin` to PATH.

Any bare `manage.py` command outside Docker Compose (`test`, `check`, `makemigrations`, ...) needs
`export DJANGO_DEBUG=1`. Without it `DEBUG` is `False` and Django raises
`RuntimeError: DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is disabled`; there is no `.env`
auto-loading.

## Project structure
```
reading/            # Django app: models, views (book_list with filtering/pagination), forms,
                    #   admin, tests.py (all tests), templatetags/, migrations/
reading_project/    # Django project config: settings.py (reads env vars), urls.py
templates/reading/  # HTML templates
static/css/         # app.css
```

## Key model facts
- `Book` statuses: `will_read`, `reading`, `read`, `deleted` (deleted is hidden from the UI)
- `rating`: decimal 1-10 in steps of 0.5, nullable
- Default ordering: `["status", "title"]`
- Generate migrations with `uv run python manage.py makemigrations`

## Environment variables
| Variable | Required | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | only if `DJANGO_DEBUG` is unset/0 | otherwise raises `RuntimeError` on startup |
| `DJANGO_DEBUG` | **yes, for any bare `manage.py` command** | `1` auto-supplies a placeholder `SECRET_KEY` |
| `DATABASE_URL` | no | omit to use SQLite (independent of `DJANGO_DEBUG`) |
| `DJANGO_ALLOWED_HOSTS` | no | comma-separated |

## Deployment
- Staging (Sirius): on push to master via deploy-staging.yml
- Production (Titan): only from a `v*` git tag on master via deploy-prod.yml (see "Releasing to prod")
- Docker Swarm with Traefik + Let's Encrypt
- Images: ghcr.io/nikpopesku/library-web (also publish legacy reading-web tags during RD-42 transition)
- Repository: https://github.com/nikpopesku/library; Jira key remains RD.
- Keep existing stack, container, volume, database and Django module names stable; see README "Project rename (RD-42)".
- Orion: no deploy pipeline — `docker-compose-orion.yml` bind-mounts this
  repo straight into the `reading-web` container (`make orion-up`), so a
  `git pull`/merge on the orion host takes effect immediately, including any
  new migration or static asset. The container's entrypoint runs `migrate`
  and `collectstatic` on every start (`RUN_STARTUP_TASKS=1`) so the DB schema
  and served CSS/JS can't drift behind the code on disk the way staging/prod
  would if a deploy step were skipped. If orion 500s with a missing relation or serves stale
  CSS/JS, restart the container (`make orion-up`) or run `make orion-migrate` /
  `make orion-collectstatic` rather than editing the DB by hand.

## Releasing to prod
Same flow as the PE repos. A tag ships **everything merged so far**, not only your ticket.

1. Merge your PR and wait for the staging deploy on the merge commit to go green.
2. Tag and push (today's date plus a counter):
   ```bash
   git fetch origin && git tag -a v2026.10.30.1 -m "RD-x, RD-y" origin/master && git push origin v2026.10.30.1
   ```
3. The tag push runs `deploy-prod.yml`. It fails before building if the commit isn't on `master` or is
   older than what is live. Deploys queue and never cancel each other. On success it creates a GitHub
   release for the tag and posts the released commits to Slack `#release`.
4. Rollback or redeploy:
   `gh workflow run deploy-prod.yml -f tag=<older-tag> -f rollback=true`.

Agents open PRs but never push release tags; tagging is the user's call.

## Code style
- Ruff: line-length 100, target py314, select E/F/I/UP/B/DJ, ignore DJ001
- Coverage: omit migrations, manage.py, asgi/wsgi
- Clean diffs, no whitespace noise in PRs
- No comments unless the WHY is non-obvious; no docstrings on obvious methods

## Code readability (all agents)

These apply to every agent and developer, not only Cursor Cloud.

- A public method should read as a short outline of the use case: a handful of calls to well-named private methods, not the implementation of every step inline.
- Keep methods small and single-purpose. If a method mixes validating, fetching, looping and building a result, split it. Rough guide: one level of nesting per method, no loop bodies longer than a few lines, and at most 30 lines per method (phpmd `ExcessiveMethodLength`).
- Extract each distinct step into a private method named for what it means in the domain (`assertAccepted`, `readCompanyId`, `isMainPlan`, `buildQuote`), not for how it is done.
- Extract conditions into predicate methods (`isMainPlan($lineItem)`) instead of inline compound conditions or tuple/array shuffling.
- Do not pass state around as positional arrays (`[$plan, $period, $properties]`). Use arrays with named keys (and an array-shape docblock) so call sites read clearly. Do not add new classes just to split up a method; add private methods.
- Do not accumulate several unrelated variables (`$main`, `$inclusive`, ...) in one loop. Classify each item in a helper and return a typed result.
- Keep long error messages and format strings out of the main flow, for example in named exception factory methods.
- Target example: `read()` = assert accepted, read company id, collect line items into main plan and inclusive plan, validate they belong together, build the quote. Each of those is its own method.
- When touching an existing long method, leave it more readable than you found it, within the scope of the ticket.
- Before finishing, run `vendor/bin/phpmd <changed php files> text phpmd.xml` (cyclomatic complexity limit 10, NPath limit 200). Never commit with `-n` / `--no-verify`, it skips the grumphp pre-commit hook that runs phpmd.

For this Python/Django repository, apply the same readability principles using idiomatic Python: `_private_method` names, named dictionary keys or typed results instead of positional state, and small single-purpose methods. The PHP-specific phpmd/grumphp command applies only when PHP files and that toolchain are present; run the repository's Ruff and Django checks for Python changes. Never bypass commit hooks.

## Branch and pull request naming
- For Jira-linked work, name the branch `<JIRA-KEY>-<short-description>`, for example `RD-26-author-duplicate-prevention`.
- Start the PR title with the same Jira key: `<JIRA-KEY>: <description>`, for example `RD-26: Prevent duplicate author creation`.
- Use the Jira key belonging to the actual task; do not invent a key or reuse an unrelated ticket. Include the Jira ticket URL in the PR description.
- These rules apply to features, fixes, documentation, tooling, and CI changes. Do not use generic `feat/`, `fix/`, `docs/`, or `chore/` branch prefixes instead of the task key.
- If no Jira ticket is associated with the work, confirm the intended task association or naming exception with the user before creating the branch or PR.
- Start each new task on a fresh branch from the latest `master`: `git switch master && git pull --ff-only origin master && git switch -c <JIRA-KEY>-<short-description>`. Preserve local changes; never discard them to switch branches.
- Never reuse a branch from a merged PR for a new task. Changes requested on an existing open PR stay on that PR's branch.
- Keep conventional commit messages as described below; Jira-prefixed branches and PR titles do not change the commit format.
- Main branch is `master`. One ticket per branch; never mix concerns.
- Open PRs for user review; never merge without explicit user approval.
- CI runs against PostgreSQL (`postgres:17-alpine`), including `makemigrations --check --dry-run`.
  Local SQLite passing does not guarantee CI passes. After pushing, check `gh pr checks --watch`
  before treating the PR as done; if a check fails, convert the PR to draft
  (`gh pr ready --undo`) and note the failure in the PR body.

## Jira status flow
- Move the ticket to **In Progress** when you start work on it, unprompted (RD-32 did this via the
  Atlassian MCP `transitionJiraIssue`: transition id `21` = In Progress, `31` = In Review).
- Move it to **In Review** as soon as the PR is open, also unprompted.
- Leave **Done** to the user; do not move a ticket to Done yourself.

## Commit format
Conventional commits: `type(scope): short description`

```
feat(books): add reading progress slider
fix(auth): handle expired session token
chore(deps): update ruff to 0.14
docs(readme): add local dev setup section
```

If no scope is applicable, omit it: `fix: correct typo in error message`.

## Local test environment (without full Docker stack)

With no `DATABASE_URL` set, settings fall back to SQLite and tests run without any setup. To match
CI and test against PostgreSQL, if Docker is available:

1. Start only the database: `docker compose -f docker-compose-local.yml --env-file .env.local up -d postgres`
2. Create `.env.local` with these vars if not already present:
   - `POSTGRES_DB=reading`
   - `POSTGRES_USER=reading`
   - `POSTGRES_PASSWORD=reading`
   - `DATABASE_URL=postgresql://reading:reading@127.0.0.1:5434/reading?sslmode=disable`
   - `DJANGO_SECRET_KEY=<any-local-dev-key>`
3. Run tests: `DATABASE_URL="$DATABASE_URL" DJANGO_DEBUG=1 DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" uv run python manage.py test`
4. Run lint/format/check the same way, or using the Makefile which calls uv directly.

The CI workflow (`.github/workflows/ci.yml`) uses these exact env vars:
- `DJANGO_DEBUG=1`
- `DJANGO_SECRET_KEY=testsecret`
- `DATABASE_URL=postgresql://reading:***@127.0.0.1:5432/reading_test?sslmode=disable`


## Migration rules
- **One migration file per PR max.** If multiple models changed, edit the generated migration to merge them, or split into separate PRs.
- If you didn't change any models but CI reports `makemigrations --check` failure, it means someone else's branch changed models and its migration was not applied to your branch's test DB — this is a false positive from parallel development. Verify by running `uv run python manage.py makemigrations` yourself; if nothing is generated (empty "No changes detected"), force-push to trigger CI again.
- Always commit `uv.lock` if `pyproject.toml` was modified (deps changed).