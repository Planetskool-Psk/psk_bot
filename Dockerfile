# Dockerfile for chatbot_be
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Expose port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the app with Gunicorn and eventlet for async
CMD ["gunicorn", "run:app", "-k", "eventlet", "-b", "0.0.0.0:5000", "--timeout", "120"]
