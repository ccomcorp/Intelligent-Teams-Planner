FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 \
    libfontconfig1 libcairo2 libgdk-pixbuf-2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/logs /app/output

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]