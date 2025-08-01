# Use NVIDIA CUDA base image for GPU support (verified available version)
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

WORKDIR /app

# Install system dependencies and Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    python3.10 \
    python3.10-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    # WeasyPrint dependencies
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libfribidi0 \
    libglib2.0-0 \
    libpangocairo-1.0-0 \
    libpango1.0-dev \
    libcairo2-dev \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Use Python 3.10 as default
RUN ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . /app/

# Make the startup script executable
RUN chmod +x /app/start.sh

# Set environment variables
ENV PYTHONPATH=/app

# Expose port for FastAPI
EXPOSE 8000

# Use the startup script as the default command
CMD ["/app/start.sh"]
