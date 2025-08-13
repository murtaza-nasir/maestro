"""
Hardware detection module for automatic GPU/CPU selection.
Supports NVIDIA CUDA, AMD ROCm, Apple Metal, and CPU fallback.
"""

import os
import platform
import subprocess
import logging
from typing import Optional, Tuple, Dict, Any
import torch

logger = logging.getLogger(__name__)


class HardwareDetector:
    """Centralized hardware detection and device management."""
    
    def __init__(self):
        self.system = platform.system()
        self.force_cpu = os.getenv("FORCE_CPU_MODE", "false").lower() == "true"
        self.preferred_device = os.getenv("PREFERRED_DEVICE_TYPE", "auto").lower()
        self._device_info = None
        
    def detect_hardware(self) -> Dict[str, Any]:
        """
        Detect available hardware and return device information.
        
        Returns:
            Dictionary containing:
            - device_type: 'cuda', 'rocm', 'mps', or 'cpu'
            - device_name: Human-readable device name
            - device_count: Number of available devices
            - memory_gb: Available memory in GB (if applicable)
            - forced: Whether CPU mode was forced
        """
        if self._device_info is not None:
            return self._device_info
            
        if self.force_cpu:
            logger.info("CPU mode forced via FORCE_CPU_MODE environment variable")
            self._device_info = {
                "device_type": "cpu",
                "device_name": "CPU (forced)",
                "device_count": 1,
                "memory_gb": self._get_cpu_memory(),
                "forced": True
            }
            return self._device_info
            
        # Check for NVIDIA CUDA
        if self._check_nvidia_cuda():
            device_info = self._get_nvidia_info()
            if device_info:
                self._device_info = device_info
                return self._device_info
                
        # Check for AMD ROCm
        if self._check_amd_rocm():
            device_info = self._get_amd_info()
            if device_info:
                self._device_info = device_info
                return self._device_info
                
        # Check for Apple Metal (MPS)
        if self._check_apple_metal():
            self._device_info = {
                "device_type": "mps",
                "device_name": "Apple Metal Performance Shaders",
                "device_count": 1,
                "memory_gb": self._get_cpu_memory(),  # Unified memory on Apple
                "forced": False
            }
            return self._device_info
            
        # Fallback to CPU
        logger.info("No GPU detected, falling back to CPU mode")
        self._device_info = {
            "device_type": "cpu",
            "device_name": "CPU (fallback)",
            "device_count": 1,
            "memory_gb": self._get_cpu_memory(),
            "forced": False
        }
        return self._device_info
        
    def _check_nvidia_cuda(self) -> bool:
        """Check if NVIDIA CUDA is available."""
        try:
            # Check PyTorch CUDA availability
            if torch.cuda.is_available():
                return True
                
            # Check nvidia-smi as fallback
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
            
    def _check_amd_rocm(self) -> bool:
        """Check if AMD ROCm is available."""
        try:
            # Check for ROCm installation
            if os.path.exists("/opt/rocm"):
                # Check if PyTorch has ROCm support
                if hasattr(torch.version, 'hip') and torch.version.hip is not None:
                    return True
                    
            # Check rocm-smi as fallback
            result = subprocess.run(
                ["rocm-smi", "--showid"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
            
    def _check_apple_metal(self) -> bool:
        """Check if Apple Metal is available."""
        if self.system != "Darwin":
            return False
            
        try:
            # Check PyTorch MPS availability
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return True
        except:
            pass
            
        return False
        
    def _get_nvidia_info(self) -> Optional[Dict[str, Any]]:
        """Get NVIDIA GPU information."""
        try:
            device_count = torch.cuda.device_count()
            if device_count == 0:
                return None
                
            # Get first GPU info
            props = torch.cuda.get_device_properties(0)
            memory_gb = props.total_memory / (1024**3)
            
            return {
                "device_type": "cuda",
                "device_name": props.name,
                "device_count": device_count,
                "memory_gb": round(memory_gb, 2),
                "forced": False
            }
        except Exception as e:
            logger.warning(f"Failed to get NVIDIA GPU info: {e}")
            return None
            
    def _get_amd_info(self) -> Optional[Dict[str, Any]]:
        """Get AMD GPU information."""
        try:
            # Try to get info via rocm-smi
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--csv"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
                
            # Parse output to get memory info
            lines = result.stdout.strip().split('\n')
            if len(lines) < 2:
                return None
                
            # Get device name
            name_result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            device_name = "AMD GPU"
            if name_result.returncode == 0:
                # Parse device name from output
                for line in name_result.stdout.split('\n'):
                    if 'Card series:' in line:
                        device_name = line.split(':')[1].strip()
                        break
                        
            return {
                "device_type": "rocm",
                "device_name": device_name,
                "device_count": 1,  # TODO: Detect multiple AMD GPUs
                "memory_gb": 16.0,  # Default, TODO: Parse from rocm-smi
                "forced": False
            }
        except Exception as e:
            logger.warning(f"Failed to get AMD GPU info: {e}")
            return None
            
    def _get_cpu_memory(self) -> float:
        """Get available system memory in GB."""
        try:
            import psutil
            memory_gb = psutil.virtual_memory().total / (1024**3)
            return round(memory_gb, 2)
        except ImportError:
            # Fallback if psutil not available
            return 8.0  # Conservative default
            
    def get_torch_device(self, device_id: Optional[int] = None) -> torch.device:
        """
        Get PyTorch device based on hardware detection.
        
        Args:
            device_id: Optional specific device ID for multi-GPU systems
            
        Returns:
            torch.device object
        """
        info = self.detect_hardware()
        device_type = info["device_type"]
        
        if device_type == "cuda":
            if device_id is not None and device_id < info["device_count"]:
                return torch.device(f"cuda:{device_id}")
            return torch.device("cuda")
        elif device_type == "rocm":
            # ROCm uses CUDA interface in PyTorch
            if device_id is not None:
                return torch.device(f"cuda:{device_id}")
            return torch.device("cuda")
        elif device_type == "mps":
            return torch.device("mps")
        else:
            return torch.device("cpu")
            
    def get_optimal_batch_size(self, base_batch_size: int = 32) -> int:
        """
        Get optimal batch size based on available hardware.
        
        Args:
            base_batch_size: Base batch size for GPU processing
            
        Returns:
            Recommended batch size
        """
        info = self.detect_hardware()
        device_type = info["device_type"]
        
        if device_type == "cpu":
            # Reduce batch size for CPU processing
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            return min(base_batch_size // 4, cpu_count * 2)
        elif device_type == "mps":
            # Apple unified memory, moderate batch size
            return base_batch_size // 2
        else:
            # GPU processing, check memory
            memory_gb = info.get("memory_gb", 8)
            if memory_gb < 8:
                return base_batch_size // 2
            elif memory_gb < 16:
                return base_batch_size
            else:
                return base_batch_size * 2
                
    def get_num_workers(self) -> int:
        """
        Get optimal number of workers for data loading.
        
        Returns:
            Recommended number of workers
        """
        info = self.detect_hardware()
        device_type = info["device_type"]
        
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        
        if device_type == "cpu":
            # Use most CPUs for processing
            return max(1, cpu_count - 2)
        else:
            # GPU processing, use fewer workers
            return min(4, cpu_count // 2)
            
    def log_device_info(self):
        """Log detected hardware information."""
        info = self.detect_hardware()
        logger.info(f"Hardware Detection Results:")
        logger.info(f"  Device Type: {info['device_type']}")
        logger.info(f"  Device Name: {info['device_name']}")
        logger.info(f"  Device Count: {info['device_count']}")
        logger.info(f"  Memory: {info['memory_gb']} GB")
        if info.get('forced'):
            logger.info(f"  Mode: Forced CPU")
            
            
# Global instance for easy access
hardware_detector = HardwareDetector()


def get_device() -> torch.device:
    """Convenience function to get PyTorch device."""
    return hardware_detector.get_torch_device()
    
    
def get_device_info() -> Dict[str, Any]:
    """Convenience function to get device information."""
    return hardware_detector.detect_hardware()