# MAESTRO Docker Setup

This document provides detailed instructions on how to run MAESTRO using Docker. For a quick start, see the Docker installation instructions in the [README.md](./README.md) file.

This guide explains how to run MAESTRO using Docker, which provides an easy way to set up and use the application without installing dependencies directly on your system.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)
- **GPU Support (Recommended)**: For optimal performance with RAG functionality
  - NVIDIA GPU with CUDA support
  - [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed

## Quick Start

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd researcher2
   ```

2. Configure your environment variables:
   ```bash
   cp ai_researcher/.env.example ai_researcher/.env
   ```
   
   Edit `ai_researcher/.env` to add your API keys and customize settings.

3. Create a directory for your PDFs:
   ```bash
   mkdir -p pdfs
   ```
   
   Copy any PDF files you want to analyze into the `pdfs` directory.

4. Start the MAESTRO Web UI:
   ```bash
   docker compose up
   ```

   This will build the Docker image and start the Streamlit web interface, accessible at http://localhost:8501

## GPU Support

MAESTRO's RAG functionality (document embedding, retrieval, and reranking) benefits significantly from GPU acceleration. The Docker setup includes GPU support by default.

### Requirements for GPU Support

1. NVIDIA GPU with CUDA support
2. NVIDIA drivers installed on your host system
3. NVIDIA Container Toolkit installed

### Verifying GPU Support

After starting the container, you can verify GPU access:

```bash
docker compose exec maestro nvidia-smi
```

If you see your GPU listed, the container has successfully accessed your GPU.

### Configuring GPU Usage

By default, the container uses GPU 0. You can change this by modifying the `CUDA_VISIBLE_DEVICES` environment variable in `docker compose.yml`:

```yaml
environment:
  - CUDA_VISIBLE_DEVICES=0,1  # Use GPUs 0 and 1
```
We recommend using a single GPU for faster startup of the RAG component. For most use-cases, this will be sufficient.

If you don't have a GPU or don't want to use it, comment out the GPU-related sections in `docker compose.yml`:

```yaml
# deploy:
#   resources:
#     reservations:
#       devices:
#         - driver: nvidia
#           count: 1
#           capabilities: [gpu]
```

## Directory Structure

The Docker setup creates several mounted volumes to persist data:

- `./ai_researcher/.env`: Your configuration file
- `./pdfs`: Place your PDF files here for ingestion
- `./cli_research_output`: Output directory for CLI research reports
- `./ui_research_output`: Output directory for UI research reports
- `maestro-data`: Docker volume for vector store and processed data

## Using the CLI

You can use the MAESTRO CLI directly through Docker:

### Document Ingestion

```bash
docker compose run --rm maestro ingest
```

Or with additional options:

```bash
docker compose run --rm maestro ingest --force-reembed
```

### Query the Vector Store

```bash
docker compose run --rm maestro query "Your query text here"
```

### Inspect the Vector Store

```bash
docker compose run --rm maestro inspect-store --list-docs
```

### Run Research

```bash
docker compose run --rm maestro run-research --question "Your research question" --output-dir /app/cli_research_output
```

Or with a file containing multiple questions:

```bash
# Create a questions.txt file
echo "Question 1" > questions.txt
echo "Question 2" >> questions.txt

# Mount the file and run research
docker compose run --rm -v $(pwd)/questions.txt:/app/questions.txt maestro run-research --input-file /app/questions.txt --output-dir /app/cli_research_output
```

### Get Help for Any Command

```bash
docker compose run --rm maestro ingest --help
docker compose run --rm maestro query --help
docker compose run --rm maestro run-research --help
```

## Using a Shell Inside the Container

If you need to access a shell inside the container:

```bash
docker compose run --rm maestro shell
```

## Using Local LLMs

The docker compose file includes a commented section for running a local LLM server using Ollama. To use it:

1. Uncomment the `local-llm` service and `ollama-data` volume in `docker compose.yml`
2. Update your `.env` file to use the local LLM:
   ```
   FAST_LLM_PROVIDER=local
   MID_LLM_PROVIDER=local
   INTELLIGENT_LLM_PROVIDER=local
   LOCAL_LLM_BASE_URL=http://local-llm:11434/api
   LOCAL_LLM_API_KEY=none
   LOCAL_LLM_FAST_MODEL=llama3
   LOCAL_LLM_MID_MODEL=llama3
   LOCAL_LLM_INTELLIGENT_MODEL=llama3
   ```
3. Start both services:
   ```bash
   docker compose up
   ```
4. Pull models in the Ollama container:
   ```bash
   docker compose exec local-llm ollama pull llama3
   ```

## Troubleshooting

### GPU Issues

If you encounter GPU-related issues:

1. Verify your NVIDIA drivers are installed and working:
   ```bash
   nvidia-smi
   ```

2. Check that the NVIDIA Container Toolkit is properly installed:
   ```bash
   sudo docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   ```

3. If you don't have a GPU or can't get it working, modify `docker compose.yml` to disable GPU support.

### Permission Issues

If you encounter permission issues with mounted volumes:

```bash
sudo chown -R $(id -u):$(id -g) ./cli_research_output ./ui_research_output
```

### Container Won't Start

If the container fails to start:

1. Check the logs:
   ```bash
   docker compose logs
   ```

2. Verify your `.env` file is properly configured.

3. Try rebuilding the image:
   ```bash
   docker compose build --no-cache
   ```

## Advanced Configuration

### Custom Embedding Models

If you want to use different embedding models, you can modify the environment variables in your `.env` file. The default is "BAAI/bge-m3".

### Persistent Storage

All data is stored in Docker volumes and mounted directories, ensuring your data persists between container restarts.

### Resource Limits

You can add resource limits to the `docker compose.yml` file if needed:

```yaml
services:
  maestro:
    # ... existing configuration ...
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

## Building a Custom Image

If you want to build and push a custom image:

```bash
docker build -t yourusername/maestro:latest .
docker push yourusername/maestro:latest
```

Then modify `docker compose.yml` to use your image instead of building locally:

```yaml
services:
  maestro:
    image: yourusername/maestro:latest
    # ... rest of configuration ...
