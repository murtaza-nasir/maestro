# CPU Mode Setup

Guide for running MAESTRO without GPU acceleration, suitable for systems without NVIDIA GPUs, AMD systems, or resource-constrained environments.

## When to Use CPU Mode

CPU mode is recommended for:

- **AMD GPU Systems** - No CUDA support available
- **Intel Graphics** - Integrated graphics only
- **macOS** - All Mac systems (no CUDA support)
- **Cloud Instances** - Without GPU allocation
- **Development/Testing** - When GPU isn't necessary
- **Resource Constraints** - Limited GPU memory

## Quick Start

### Method 1: CPU-Only Docker Compose

The simplest way to run in CPU mode:

```bash
# Use dedicated CPU configuration
docker compose -f docker-compose.cpu.yml up -d --build
```

This configuration:
  - Automatically configures for CPU processing
  - Removes all GPU-related settings
  - Optimizes for CPU performance

### Method 2: Force CPU Mode via Environment

Add to your `.env` file:

```bash
# Force CPU mode for all operations
FORCE_CPU_MODE=true

# Optional: Explicitly set device type to CPU
PREFERRED_DEVICE_TYPE=cpu
```

Then start normally:

```bash
docker compose up -d --build
```

## Performance Optimization

### CPU Configuration

Optimize CPU performance in `.env`:

```bash
# Thread configuration
MAX_WORKER_THREADS=8            # Set to number of CPU cores
```

### Recommended System Specs

#### Minimum Requirements
- **CPU**: 8 cores (16 threads)
- **RAM**: 16GB
- **Storage**: 20GB free space

#### Recommended Requirements
- **CPU**: 12+ cores (24+ threads)
- **RAM**: 32GB+
- **Storage**: 50GB+ free space

## Platform-Specific Setup

### Linux CPU Mode

```bash
# Check CPU information
lscpu

# Start with CPU mode
docker compose -f docker-compose.cpu.yml up -d --build
```

### Windows CPU Mode

```powershell
# Check CPU information
wmic cpu get name,numberofcores,numberoflogicalprocessors

# Use CPU-only configuration
docker compose -f docker-compose.cpu.yml up -d --build
```

### macOS (Always CPU Mode)

All Macs run in CPU mode (no CUDA support):

```bash
# Check CPU info
sysctl -n machdep.cpu.brand_string
sysctl -n hw.ncpu

# Start with CPU configuration
docker compose -f docker-compose.cpu.yml up -d --build
```

## Embedding Model Discussion

MAESTRO uses BGE-M3 embeddings for document processing. In CPU mode:

### Embedding Performance

The BGE-M3 model runs on CPU but is significantly slower than GPU:

- **Document chunking**: Efficient on CPU
- **Embedding generation**: 5-10x slower on CPU
- **First-time model download**: ~2GB download

### Optimization Tips

1. **Process documents in batches** during off-hours
2. **Use persistent model cache** to avoid re-downloads:
   ```yaml
   volumes:
     - ./maestro_model_cache:/root/.cache/huggingface
   ```
3. **Pre-process documents** before peak usage

## Performance Expectations

### Processing Times (Approximate)

| Task | GPU | CPU (8 cores) | CPU (16 cores) |
|------|-----|---------------|----------------|
| PDF Processing (10 pages) | 30s | 5-15 min | 3-12 min |
| Document Embedding (1000 chunks) | 1 min | 10-20 min | 5-10 min |
| Reranking (100 docs) | 5s | 30-60s | 15-30s |

### Memory Usage

CPU mode memory requirements:

- **Idle**: 2-3GB
- **Processing**: 4-8GB
- **Peak (large docs)**: 8-16GB

## CPU vs GPU Comparison

### Reliability
- **CPU**: Always works, platform independent
- **GPU (NVIDIA)**: Excellent when available, requires specific hardware

### Performance
- **Document Processing**: GPU is 10-30x faster
- **Embedding Generation**: GPU is significantly faster
- **Chat Operations**: Minimal difference (uses external AI APIs)

### When CPU Mode is Fine
- Small document libraries (<100 documents)
- Infrequent document uploads
- Development and testing
- When GPU resources needed elsewhere

### When GPU is Recommended
- Large document libraries (>1000 documents)
- Frequent document processing
- Regular use

## Troubleshooting CPU Mode

### High CPU Usage

Normal during document processing. To reduce:

```bash
# Limit worker threads in .env
MAX_WORKER_THREADS=4
```

### Slow Processing

Expected in CPU mode. Tips:

1. Process documents in smaller batches
2. Schedule processing during off-hours
3. Consider cloud GPU instances for bulk processing

### Memory Issues

If running out of memory:

```bash
# Reduce parallel processing
MAX_WORKER_THREADS=2

# Restart containers
docker compose down
docker compose -f docker-compose.cpu.yml up -d
```

## Docker Resource Limits

Set resource limits for CPU mode:

```yaml
# In docker-compose.cpu.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

## Monitoring Performance

Check resource usage:

```bash
# Monitor Docker containers
docker stats

# Check specific service
docker stats maestro-backend
```

## Next Steps

- [Configure AI Providers](../configuration/ai-providers.md)
- [Optimize Settings for CPU](../../user-guide/settings/research-config.md)
- [Document Processing Tips](../../user-guide/documents/overview.md)
- [CLI Usage Guide](cli-commands.md)