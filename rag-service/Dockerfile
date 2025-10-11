FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for text processing and ML
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
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
RUN useradd -m -u 1000 raguser && chown -R raguser:raguser /app
USER raguser

# Expose port
EXPOSE 7120

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7120/health || exit 1

# Run the application
CMD ["poetry", "run", "python", "-m", "src.main"]