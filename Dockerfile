# Use NVIDIA CUDA base image for GPU support
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

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
    && rm -rf /var/lib/apt/lists/*

# Use Python 3.10 as default
RUN ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# Copy requirements first for better caching
COPY ai_researcher/requirements.txt /app/ai_researcher/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r ai_researcher/requirements.txt && \
    pip install --no-cache-dir lxml_html_clean linkup-sdk
    
# Copy the application code
COPY . /app/

# Create necessary directories
RUN mkdir -p /app/ai_researcher/data/raw_pdfs \
    /app/ai_researcher/data/processed/markdown \
    /app/ai_researcher/data/processed/metadata \
    /app/ai_researcher/data/vector_store \
    /app/ai_researcher/data/mission_results \
    /app/cli_research_output \
    /app/ui_research_output

# Set environment variables
ENV PYTHONPATH=/app

# Create a volume for data persistence
VOLUME ["/app/ai_researcher/data", "/app/cli_research_output", "/app/ui_research_output"]

# Expose port for Streamlit
EXPOSE 8501

# Set the entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
