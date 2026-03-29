FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YEAR_HOST=0.0.0.0 \
    YEAR_PORT=8000 \
    YEAR_DB_PATH=/data/year.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./
COPY static ./static

RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "server.py"]
