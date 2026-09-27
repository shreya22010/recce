# Chromium for the PDF and the system libraries WeasyPrint needs. Both are the
# reason a plain Python host does not work: the PDF is a headline feature and it
# silently disappears without one of them.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    RECCE_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
      libffi-dev shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so a code change does not reinstall torch every build.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CHROME_BIN=/usr/bin/chromium
EXPOSE 8010
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8010}"]
