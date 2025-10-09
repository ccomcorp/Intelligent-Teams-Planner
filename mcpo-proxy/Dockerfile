FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.8.2

# Configure Poetry: Don't create a virtual environment, install dependencies globally
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy Poetry files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install dependencies using Poetry
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# Copy application code
COPY src/ ./src/
COPY README.md ./

# Create non-root user
RUN useradd -m -u 1000 proxyuser && chown -R proxyuser:proxyuser /app
USER proxyuser

# Expose port
EXPOSE 7105

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7105/health || exit 1

# Run the application
CMD ["poetry", "run", "python", "-m", "src.main"]