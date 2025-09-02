# Installation Overview

This section provides comprehensive installation instructions for MAESTRO across different platforms and configurations.

!!! tip "Quick Installation"
    All platforms follow the same basic steps:
    
    1. **Install Docker** (Docker Desktop for Windows/macOS, Docker Engine for Linux)
    2. **Clone the repository**
    3. **Run setup script** (`setup-env.sh` or `setup-env.ps1`)
    4. **Start with Docker Compose**
    
    Docker Desktop handles all complexity on Windows and macOS!

## Choose Your Installation Method

### By Operating System

<div class="grid cards" markdown>

-   **[Linux Installation](linux.md)**
    
    Full installation guide for Linux distributions with GPU support

-   **[macOS Installation](macos.md)**
    
    Installation for Apple Silicon and Intel Macs

-   **[Windows Installation](windows.md)**
    
    Simple Windows setup with Docker Desktop (handles WSL2 automatically)

</div>

### Special Configurations

<div class="grid cards" markdown>

-   **[CPU Mode Setup](cpu-mode.md)**
    
    Running MAESTRO without GPU acceleration

-   **[Database Reset](database-reset.md)**
    
    How to reset and reinitialize the database

-   **[CLI Commands](cli-commands.md)**
    
    Useful command-line tools and utilities

</div>

## System Requirements

### Minimum Requirements

- **Operating System**: 
    - Linux (any modern distribution)
    - macOS (Intel or Apple Silicon)
    - Windows 10/11 (Docker Desktop handles WSL2 automatically)
- **RAM**: 16GB minimum
- **Storage**: ~30GB free space
- **CPU**: 8 cores or more
- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher

### Recommended Requirements

- **RAM**: 32GB or more
- **Storage**: 50GB+ (8GB models + space for document libraries)
- **CPU**: 12 cores or more
- **GPU**: NVIDIA GPU with CUDA support (strongly recommended)
    - 4GB VRAM minimum for single process operation
    - 8GB VRAM recommended for concurrent research + document processing
    - BGE-M3 (560M params): ~1.3GB VRAM per instance
    - BGE-Reranker-v2-m3: ~1.2GB VRAM
    - MultiGPU system recommended if also hosting LLMs locally
- **Network**: Stable broadband connection for web search

## Pre-Installation Checklist

Before proceeding with installation:

1. **Install Docker**

    - **Windows/macOS**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes everything you need)
    - **Linux**: [Docker Engine](https://docs.docker.com/engine/install/)
    
    !!! note "Windows Users"
        Docker Desktop automatically configures WSL2 backend - no manual WSL setup needed!

2. **Verify Docker Installation**
   ```bash
   docker --version
   docker compose version
   ```

3. **Obtain API Keys**
    You'll need at least one AI provider API key:
    - [OpenAI](https://platform.openai.com/api-keys)
    - [Openrouter](https://openrouter.ai/settings/keys)
    - Self hosted LLM - use a dummy API key if none needed

4. **Check Available Ports**
    
    MAESTRO uses these default ports:

    - Port 80: Web interface (nginx)
    - Port 5432: PostgreSQL database

## Installation Methods Comparison

| Method | GPU Support | Complexity | Performance | Best For |
|--------|------------|------------|-------------|----------|
| Linux | Full | Easy | Excellent | Reliable performance |
| macOS | No (CPU only) | Easy | Good | Reasonable performance |
| Windows (Docker Desktop) | Limited | Easy | Good | Windows users |
| CPU Mode | No | Easy | Moderate | Systems without GPU |

!!! success "Windows Installation Simplified"
    Docker Desktop makes Windows installation as easy as macOS - it handles all WSL2 configuration automatically!

## Docker Compose Profiles

MAESTRO supports different deployment profiles:

### Default Profile
```bash
docker compose up -d --build
```
Runs with automatic GPU detection if available.

### CPU-Only Profile
```bash
docker compose -f docker-compose.cpu.yml up -d --build
```
Forces CPU mode, useful for systems without GPU.

## Network Configuration Options

The setup script offers three network configurations:

### 1. Simple (Localhost Only)
- Access only from the same machine
- URL: `http://localhost`
- Most secure option

### 2. Network Access
- Access from other devices on your network
- URL: `http://[your-ip-address]`
- Good for team deployments

### 3. Custom Domain
- Use with reverse proxies
- Custom URLs like `http://maestro.local`
- Best for set-and-forget deployments

## Post-Installation Steps

After successful installation:

1. **Verify All Services Running**
   ```bash
   docker compose ps
   ```

2. **Check Logs for Errors**
   ```bash
   docker compose logs
   ```

3. **Access Web Interface**
    - Navigate to configured URL
    - Default: `http://localhost`

4. **Login with Default Credentials**
    - Username: `admin`
    - Password: `admin123`

5. **Immediate Security Steps**
    - Change default password
    - Configure user accounts
    - Set up API keys

## Troubleshooting Quick Reference

### Service Won't Start
- Check Docker is running
- Verify ports are available
- Review logs: `docker compose logs [service-name]`

### Cannot Access Web Interface
- Ensure all services are running
- Check firewall settings
- Verify network configuration

### Database Connection Issues
- PostgreSQL container must be healthy
- Check database credentials in `.env`
- Ensure proper network connectivity

## Getting Help

If you encounter issues:

1. Check the specific platform guide for your OS
2. Review [Troubleshooting Guide](../../troubleshooting/index.md)
3. Search [GitHub Issues](https://github.com/murtaza-nasir/maestro/issues)
4. Ask in [Community Forum](https://github.com/murtaza-nasir/maestro/discussions)

## Next Steps

Choose your platform-specific guide:

- **[Linux Installation](linux.md)** - For Linux users (full GPU support)
- **[macOS Installation](macos.md)** - For Mac users (CPU only)
- **[Windows Installation](windows.md)** - For Windows users (Docker Desktop makes it easy!)
- **[CPU Mode Setup](cpu-mode.md)** - For systems without GPU