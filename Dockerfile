FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YEAR_HOST=0.0.0.0 \
    YEAR_PORT=8000 \
    YEAR_DB_PATH=/data/year.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy static assets and source files separately
COPY static/ ./static/
COPY src/ ./src/

# Ensure the data directory exists for the SQLite database
RUN mkdir -p /data

EXPOSE 8000

# Set Python path to find modules in src/ and start server from root
ENV PYTHONPATH=/app/src
CMD ["python", "src/server.py"]
