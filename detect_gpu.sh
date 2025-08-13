#!/bin/bash

# Detect if GPU is available and which platform we're on
detect_gpu() {
    # Check if CPU mode is forced via environment variable
    if [[ "${FORCE_CPU_MODE}" == "true" ]]; then
        echo "cpu_forced"
        return
    fi
    
    # Check if we're on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS doesn't support NVIDIA Docker runtime but may support Metal
        echo "mac"
        return
    fi
    
    # Check for NVIDIA GPU on Linux/Windows
    if command -v nvidia-smi &> /dev/null; then
        # Check if nvidia-container-toolkit is installed
        if docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &> /dev/null 2>&1; then
            echo "nvidia"
            return
        fi
        # NVIDIA GPU detected but Docker runtime not available
        if nvidia-smi &> /dev/null; then
            echo "nvidia_no_docker"
            return
        fi
    fi
    
    # Check for AMD GPU with ROCm support
    if command -v rocm-smi &> /dev/null; then
        # Check if ROCm is properly installed
        if rocm-smi --showid &> /dev/null; then
            echo "amd_rocm"
            return
        fi
    fi
    
    # Check for AMD GPU via lspci (fallback detection)
    if command -v lspci &> /dev/null; then
        if lspci | grep -i "VGA.*AMD\|Display.*AMD" &> /dev/null; then
            echo "amd_detected"
            return
        fi
    fi
    
    # No GPU support detected
    echo "cpu"
}

# Export the result
GPU_SUPPORT=$(detect_gpu)
echo "GPU_SUPPORT=$GPU_SUPPORT"