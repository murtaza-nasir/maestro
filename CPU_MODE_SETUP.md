# CPU Mode Setup Guide for AMD Systems

This guide explains how to configure Maestro to run in CPU-only mode, which is particularly useful for AMD GPU systems without ROCm support or systems with limited GPU resources.

## Quick Start

### Method 1: Using Environment Variables

1. **Create your `.env` file** (if not already created):
   ```bash
   cp .env.example .env
   ```

2. **Enable CPU mode** by adding these lines to your `.env` file:
   ```bash
   # Force CPU mode for all operations
   FORCE_CPU_MODE=true
   
   # Optional: Explicitly set device type to CPU
   PREFERRED_DEVICE_TYPE=cpu
   ```

3. **Start the application**:
   ```bash
   docker-compose up -d
   ```

### Method 2: Using CPU-Only Docker Compose

We provide a dedicated CPU-only Docker Compose configuration that doesn't require any GPU drivers:

```bash
# Use the CPU-only configuration
docker-compose -f docker-compose.cpu.yml up -d
```

This configuration automatically sets `FORCE_CPU_MODE=true` and removes all GPU-related settings.

## Hardware Detection

The system now includes automatic hardware detection that supports:
- **NVIDIA GPUs** with CUDA
- **AMD GPUs** with ROCm (if installed)
- **Apple Silicon** with Metal Performance Shaders
- **CPU fallback** for any system

The detection script (`detect_gpu.sh`) will automatically identify your hardware and configure the system appropriately.

## Configuration Options

### Environment Variables

| Variable | Description | Options | Default |
|----------|-------------|---------|---------|
| `FORCE_CPU_MODE` | Force CPU-only operation | `true`, `false` | `false` |
| `PREFERRED_DEVICE_TYPE` | Preferred acceleration type | `auto`, `cuda`, `rocm`, `mps`, `cpu` | `auto` |
| `CUDA_DEVICE` | GPU device index (if using GPU) | `0`, `1`, `2`, etc. | `0` |

### Hardware Detection Module

The new `hardware_detection.py` module provides:
- Automatic device selection
- Optimized batch sizes based on hardware
- CPU thread optimization
- Memory management for different device types

## Performance Optimization

When running in CPU mode, the system automatically:

1. **Adjusts batch sizes** to optimize for CPU processing
2. **Sets thread counts** based on available CPU cores
3. **Reduces memory requirements** for model loading
4. **Optimizes data loading** workers

## AMD GPU Support

### With ROCm (Experimental)

If you have ROCm installed, the system will attempt to use it automatically. No additional configuration is needed.

### Without ROCm

For AMD GPUs without ROCm support, use CPU mode as described above. This provides stable operation while AMD GPU support is being developed.

## Running Without Docker

If running directly without Docker:

1. **Set environment variables**:
   ```bash
   export FORCE_CPU_MODE=true
   export PREFERRED_DEVICE_TYPE=cpu
   ```

2. **Run the application**:
   ```bash
   python maestro_backend/main.py
   ```

## Verifying CPU Mode

To verify that CPU mode is active, check the startup logs:

```bash
docker-compose logs backend | grep -i "cpu"
```

You should see messages like:
- "CPU mode forced via FORCE_CPU_MODE environment variable"
- "Hardware Detection Results: Device Type: cpu"
- "Set PyTorch threads to X for CPU processing"

## Performance Considerations

### CPU Mode Performance

- **Embedding generation** will be slower (expect 2-5x slower than GPU)
- **Document processing** may take longer for large PDFs
- **Reranking** operations will have increased latency
- Consider reducing batch sizes in your settings for better responsiveness

### Recommended Settings for CPU Mode

Add these to your `.env` file for optimal CPU performance:

```bash
# Reduce batch sizes for CPU processing
EMBEDDING_BATCH_SIZE=4
MAX_CONCURRENT_REQUESTS=2

# Adjust worker threads based on your CPU
MAX_WORKER_THREADS=8
```

## Troubleshooting

### Issue: Out of Memory Errors

**Solution**: Reduce batch sizes and concurrent operations:
```bash
EMBEDDING_BATCH_SIZE=2
MAX_CONCURRENT_REQUESTS=1
```

### Issue: Slow Processing

**Solution**: Ensure you have sufficient CPU cores and RAM:
- Minimum recommended: 8 CPU cores, 16GB RAM
- Optimal: 16+ CPU cores, 32GB+ RAM

### Issue: Docker Still Trying to Use GPU

**Solution**: Use the CPU-only Docker Compose file:
```bash
docker-compose -f docker-compose.cpu.yml up -d
```

## Community Contributions

The CPU mode implementation was developed with community feedback from users with AMD systems. Special thanks to @palgrave for testing and providing feedback on AMD CPU optimization.

## Future Development

We're working on:
- Native AMD ROCm support
- Further CPU optimizations
- Support for AMD integrated graphics (APUs)
- Automatic performance tuning based on hardware

## Getting Help

If you encounter issues with CPU mode:

1. Check the [GitHub Issues](https://github.com/murtaza-nasir/maestro/issues)
2. Create a new issue with:
   - Your system specifications (CPU, RAM, OS)
   - The error messages you're seeing
   - Your `.env` configuration (remove sensitive data)

## Contributing

If you've successfully set up CPU mode on your AMD system and want to share optimizations:

1. Fork the repository
2. Create a branch with your improvements
3. Submit a pull request with details about your setup and performance gains