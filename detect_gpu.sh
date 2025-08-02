#!/bin/bash

# Detect if GPU is available and which platform we're on
detect_gpu() {
    # Check if we're on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS doesn't support NVIDIA Docker runtime
        echo "mac"
        return
    fi
    
    # Check for NVIDIA GPU on Linux/Windows
    if command -v nvidia-smi &> /dev/null; then
        # Check if nvidia-container-toolkit is installed
        if docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &> /dev/null; then
            echo "nvidia"
            return
        fi
    fi
    
    # No GPU support detected
    echo "cpu"
}

# Export the result
GPU_SUPPORT=$(detect_gpu)
echo "GPU_SUPPORT=$GPU_SUPPORT"