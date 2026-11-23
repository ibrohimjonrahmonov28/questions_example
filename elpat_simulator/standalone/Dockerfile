# Build from the elpat_simulator/ folder:  docker build -f standalone/Dockerfile -t elpat .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 ELPAT_FRONTEND_DIR=/app
WORKDIR /app/standalone
COPY standalone/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY index.html /app/index.html
COPY pics /app/pics
COPY standalone /app/standalone
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
 && useradd --create-home --uid 10001 elpat
USER elpat
EXPOSE 8000
# Threads suit this I/O-bound app (waiting on Claude and speech-to-text); the final rating call can take up to ~2 minutes.
CMD gunicorn elpat_server.wsgi --bind 0.0.0.0:${PORT} --workers 2 --threads 8 --timeout 180 --access-logfile -
