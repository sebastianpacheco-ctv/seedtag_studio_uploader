# Use a lightweight official Python runtime as base image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install dependencies including Gunicorn for production serving
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application directories into the container
COPY app/ ./app/
COPY reference/ ./reference/

# Set working directory to the app directory so references resolve correctly
# Note: reference/ is at the sibling level of app/, so we keep the root as python path
ENV PYTHONPATH=/app/reference:/app

# Configure default Cloud Run environment variables
ENV PORT=8080
EXPOSE 8080

# Configure production-ready Flask parameters
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV TMP_DIR=/tmp

# Start Gunicorn WSGI server
# binds to the port provided by Cloud Run ($PORT)
# chdir to app directory so app:app resolves cleanly
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 --chdir app app:app
