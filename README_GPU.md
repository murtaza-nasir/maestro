# Maestro GPU Support Guide

## Overview

Maestro now includes automatic GPU detection and configuration for optimal performance across different platforms.

## Features

- **Automatic Platform Detection**: Detects macOS, Linux with NVIDIA GPUs, or CPU-only systems
- **Dynamic Configuration**: Automatically enables GPU support when available
- **Cross-Platform Compatibility**: Works seamlessly on Mac, Linux, and Windows (WSL2)

## Quick Start

### Using the Start Script (Recommended)

```bash
# Start Maestro with automatic GPU detection
./start.sh

# Stop Maestro
./stop.sh
```

### Manual Docker Compose

```bash
# CPU-only mode
docker-compose up -d

# With GPU support (Linux/Windows with NVIDIA GPU)
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Platform-Specific Notes

### macOS
- Runs in CPU mode (NVIDIA Docker runtime not supported on macOS)
- Optimized for Apple Silicon and Intel Macs
- Uses standard Docker Desktop

### Linux with NVIDIA GPU
- Automatically detects and enables GPU support
- Requires nvidia-container-toolkit installed
- Distributes load across multiple GPUs if available

### Windows (WSL2)
- Requires WSL2 with GPU support enabled
- Works with NVIDIA GPUs through WSL2
- Follow Microsoft's WSL2 GPU guide for setup

## Configuration

### GPU Device Assignment

Edit `.env` to assign specific GPUs to services:

```env
# GPU device IDs (0, 1, 2, etc.)
BACKEND_GPU_DEVICE=0
DOC_PROCESSOR_GPU_DEVICE=0
CLI_GPU_DEVICE=0
```

### Environment Variables

The system sets `GPU_AVAILABLE` environment variable:
- `true`: GPU support is enabled
- `false`: Running in CPU mode

## Troubleshooting

### Check GPU Detection
```bash
./detect_gpu.sh
```

### Verify GPU in Docker
```bash
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### View Service Logs
```bash
docker-compose logs backend
docker-compose logs doc-processor
```

## Performance Tips

1. **Multi-GPU Setup**: Distribute services across different GPUs by setting different device IDs
2. **CPU Mode**: Still performant for smaller workloads and development
3. **Memory Management**: Monitor GPU memory usage with `nvidia-smi`

## Requirements

### For GPU Support
- NVIDIA GPU with CUDA support
- nvidia-docker2 or nvidia-container-toolkit
- Docker 19.03+ with GPU support

### For CPU Mode
- Docker Desktop (Mac/Windows) or Docker Engine (Linux)
- No additional requirements