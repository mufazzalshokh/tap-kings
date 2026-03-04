FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY frontend/ ../frontend/

EXPOSE 8000

# Shell form so $PORT environment variable expands correctly on Railway
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}