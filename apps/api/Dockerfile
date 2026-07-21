# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install system dependencies needed for OpenCV, Pillow, and PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# Expose server port
EXPOSE 8000

# Run FastAPI app with Gunicorn and Uvicorn workers
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "python:app.config", "-b", "0.0.0.0:8000", "--workers", "4", "app.main:app"]
