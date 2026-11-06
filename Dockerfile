FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM python:3.14.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     UV_COMPILE_BYTECODE=1     UV_LINK_MODE=copy     PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update     && apt-get upgrade -y --no-install-recommends     && apt-get install -y --no-install-recommends libpq5     && rm -rf /var/lib/apt/lists/*

# The app installs via uv into /app/.venv; system pip is unused and ships vulnerable vendored libs.
RUN python -m pip uninstall -y pip

COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

RUN addgroup --system app && adduser --system --ingroup app app

COPY . .
RUN DJANGO_SECRET_KEY=build-only-staticfiles-key python manage.py collectstatic --noinput

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["gunicorn", "reading_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

EXPOSE 8000
