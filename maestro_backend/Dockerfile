# Use NVIDIA CUDA base image for GPU support (compatible with driver 575.x)
FROM nvidia/cuda:12.9.1-base-ubuntu24.04

WORKDIR /app

# Install system dependencies and Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-venv \
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
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies in virtual environment
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . /app/

# Fix line endings for shell scripts (for Windows users)
RUN find /app -type f -name "*.sh" -exec dos2unix {} \;

# Make the startup script executable
RUN chmod +x /app/start.sh

# Set environment variables
ENV PYTHONPATH=/app

# Expose port for FastAPI
EXPOSE 8000

# Use the startup script as the default command
CMD ["/app/start.sh"]
