FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . .
RUN chmod +x scripts/boot.sh
ENV UK_ETDI_CONFIG_DIR=/srv/config PYTHONUNBUFFERED=1 APP_ENV=production PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "scripts/boot.sh"]
