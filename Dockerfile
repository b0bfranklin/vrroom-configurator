FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg for video analysis
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -r appuser

# Copy application code
COPY app.py .
COPY templates/ templates/

# Create directories for uploads and exports
RUN mkdir -p uploads exports && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
