# Technting CMS container images.
#
#   app  the dashboard (gunicorn), also used for the scheduler service
#   web  nginx: the published static site, plus a proxy in front of the dashboard that serves its static files
#
# Build both with docker compose (see docker-compose.yml and docs/INSTALL.md).

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- app
FROM python:${PYTHON_VERSION}-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TECHNTING_CMS_VAR_DIR=/data/var \
    TECHNTING_CMS_OUTPUT_DIR=/srv/site \
    TECHNTING_CMS_STATIC_ROOT=/app/staticfiles \
    GUNICORN_CMD_ARGS="--workers 2 --threads 2 --timeout 60 --access-logfile - --error-logfile -"

RUN groupadd --system --gid 10001 technting \
 && useradd --system --uid 10001 --gid technting --home-dir /data --shell /usr/sbin/nologin technting

# Database client tools for backups and restores (mariadb-dump / mariadb, pg_dump / psql) and the MySQL client
# library. Both optional drivers are in the image, so MySQL, MariaDB and PostgreSQL only need TECHNTING_CMS_DB_*
# settings. pg_dump must be the same major version as the PostgreSQL server or newer.
RUN apt-get update  && apt-get install -y --no-install-recommends mariadb-client postgresql-client libmariadb3  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-mysql.txt requirements-postgresql.txt ./
# mysqlclient is compiled here; the compiler and headers are removed again in the same layer
RUN apt-get update  && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev  && pip install -r requirements.txt -r requirements-mysql.txt -r requirements-postgresql.txt  && apt-get purge -y --auto-remove build-essential pkg-config default-libmysqlclient-dev  && rm -rf /var/lib/apt/lists/*

COPY . .
RUN chmod 0755 deploy/docker/entrypoint.sh \
 && TECHNTING_CMS_SECRET_KEY=build-only TECHNTING_CMS_VAR_DIR=/tmp/build-var python manage.py collectstatic --noinput \
 && rm -rf /tmp/build-var \
 && python -m compileall -q cms crm shield formbuilder technting_cms plugins \
 && mkdir -p /data/var /data/backups /srv/site \
 && chown -R technting:technting /data /srv/site

USER technting
VOLUME ["/data", "/srv/site"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "/app/deploy/docker/healthcheck.py"]

ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
CMD ["web"]

# ---------------------------------------------------------------- web
FROM nginx:1.27-alpine AS web

COPY --from=app /app/staticfiles /usr/share/technting/static
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/docker/web-start.sh /usr/local/bin/web-start.sh
RUN chmod 0755 /usr/local/bin/web-start.sh && mkdir -p /srv/site

EXPOSE 8000 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
CMD ["/usr/local/bin/web-start.sh"]
