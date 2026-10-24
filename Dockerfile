FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app app

WORKDIR /app

COPY foodplanner/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY foodplanner/ /app/
COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py

RUN mkdir -p /data /app/staticfiles \
    && chown -R app:app /data /app/staticfiles

EXPOSE 8000

ENTRYPOINT ["python", "/usr/local/bin/docker-entrypoint.py"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
