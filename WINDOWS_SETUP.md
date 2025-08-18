# MAESTRO Windows Setup Guide

This guide will help you set up and run MAESTRO on Windows systems.

## Prerequisites

### 1. Docker Desktop for Windows
- Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- Ensure Docker Desktop is running and configured for Windows containers
- Verify installation by running `docker --version` in Command Prompt or PowerShell

### 2. Git for Windows
- Download and install [Git for Windows](https://git-scm.com/download/win)
- Ensure Git is added to your system PATH

### 3. PowerShell (Recommended)
- Windows 10/11 comes with PowerShell 5.1 or later
- For better experience, consider installing [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)

## Installation Steps

### 1. Clone the Repository
```powershell
# Using PowerShell (recommended)
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro

# Or using Command Prompt
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
```

### 2. Environment Setup

#### Option A: PowerShell Script (Recommended)
```powershell
# Run the PowerShell setup script
.\setup-env.ps1
```
This script will automatically:
- Copy `.env.example` to `.env`
- Generate secure passwords
- Configure network settings
- Set up GPU configuration

#### Option B: Manual Setup
```powershell
# Copy the environment template
copy .env.example .env

# Edit the .env file with your preferred text editor
notepad .env
```

### 3. Start MAESTRO

#### For Systems with NVIDIA GPUs
```powershell
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

#### For CPU-Only Systems (Recommended for most Windows users)
```powershell
# Use the CPU-optimized compose file
docker compose -f docker-compose.cpu.yml up -d

# View logs
docker compose -f docker-compose.cpu.yml logs -f

# Stop services
docker compose -f docker-compose.cpu.yml down
```

#### Using Individual Commands
```powershell
# Build and start backend
docker compose up -d backend

# Build and start frontend
docker compose up -d frontend

# Start document processor
docker compose up -d doc-processor
```

## CLI Operations

MAESTRO provides Windows-compatible CLI tools for document management:

### Using PowerShell Script (Recommended)
```powershell
# Show help
.\maestro-cli.ps1 help

# Create a user
.\maestro-cli.ps1 create-user researcher mypass123 -FullName "Research User"

# Create a document group
.\maestro-cli.ps1 create-group researcher "AI Papers" -Description "Machine Learning Research"

# Process PDF documents
.\maestro-cli.ps1 ingest researcher ./pdfs

# Check status
.\maestro-cli.ps1 status -Username researcher

# Search documents
.\maestro-cli.ps1 search researcher "machine learning" -Limit 10
```


## Configuration

### Environment Variables

The main configuration file is `.env`, created from `.env.example`. Key settings include:

#### Basic Configuration
```env
# Main application port (the only port you need to configure)
MAESTRO_PORT=80  # Change this if port 80 is in use

# Timezone configuration
TZ=America/Chicago
VITE_SERVER_TIMEZONE=America/Chicago

# Admin credentials (CHANGE THESE!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123  # Must change for security

# JWT Secret (generate a secure random string)
JWT_SECRET_KEY=your-secret-key-change-this
```

#### GPU Configuration
```env
# For GPU acceleration (NVIDIA GPUs only)
BACKEND_GPU_DEVICE=0
DOC_PROCESSOR_GPU_DEVICE=0
CLI_GPU_DEVICE=0

# For CPU-only mode (no GPU or AMD GPUs)
FORCE_CPU_MODE=true  # Uncomment to disable GPU
```

#### Database Configuration
```env
# PostgreSQL settings (auto-configured by setup script)
POSTGRES_USER=maestro_user
POSTGRES_PASSWORD=secure_generated_password
POSTGRES_DB=maestro_db
```

### GPU Support

To enable GPU acceleration on Windows:

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
2. Set GPU device IDs in `.env`:
   ```env
   BACKEND_GPU_DEVICE=0
   DOC_PROCESSOR_GPU_DEVICE=0
   CLI_GPU_DEVICE=0
   ```
3. Use `all` to use all available GPUs

## Troubleshooting

### Common Issues

#### 1. Line Ending Issues (CRITICAL FOR WINDOWS)
```powershell
# If you see "bad interpreter" or similar errors:
.\\fix-line-endings.ps1

# Then rebuild the backend:
docker compose down
docker compose build --no-cache maestro-backend
docker compose up -d
```

#### 2. Docker Not Running
```powershell
# Check Docker status
docker --version
docker compose version

# Start Docker Desktop if not running
# Open Docker Desktop application
```

#### 3. Port Conflicts
If port 80 is already in use:
```powershell
# Check what's using port 80
netstat -ano | findstr :80

# Change port in .env file
MAESTRO_PORT=8080  # or any available port
```

#### 4. Permission Issues
```powershell
# Run PowerShell as Administrator if needed
# Or adjust file permissions for the project directory
```

#### 5. Path Issues
```powershell
# Use forward slashes or escaped backslashes in paths
PDF_DIR=./pdfs
# or
PDF_DIR=.\\pdfs
```

#### 6. Script Execution Policy
If PowerShell scripts won't run:
```powershell
# Check execution policy
Get-ExecutionPolicy

# Set execution policy (run as Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Logs and Debugging

#### View Service Logs
```powershell
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f doc-processor
```

#### Debug CLI Operations
```powershell
# Run CLI with verbose output
docker compose --profile cli run --rm cli python cli_ingest.py --help
```

## File Structure

```
maestro/
├── maestro-cli.ps1          # Windows PowerShell CLI script
├── setup-env.ps1            # Windows PowerShell setup script
├── fix-line-endings.ps1     # Windows line ending fix script
├── .env.example             # Environment template with all options
├── .env                     # Your environment configuration (created from .env.example)
├── docker-compose.yml       # Main Docker services configuration
├── docker-compose.cpu.yml   # CPU-only configuration
├── maestro_backend/
│   ├── data/                # Persistent data storage
│   └── Dockerfile           # Backend container definition
├── maestro_frontend/
│   └── Dockerfile           # Frontend container definition
├── nginx/                   # Reverse proxy configuration
│   └── nginx.conf           # Routing rules
└── reports/                 # Generated research reports
```

## Performance Optimization

### Windows-Specific Optimizations

1. **Docker Desktop Settings**:
   - Increase memory allocation (recommended: 8GB+)
   - Increase CPU allocation (recommended: 4+ cores)
   - Enable WSL 2 backend for better performance

2. **File System Performance**:
   - Store project on fast storage (SSD recommended)
   - Use Windows paths with proper escaping

3. **Network Configuration**:
   - Use `127.0.0.1` instead of `localhost` for better performance
   - Configure firewall exceptions if needed

## Security Considerations

1. **Environment Variables**:
   - Never commit `.env` files to version control
   - Use strong JWT secrets in production
   - Keep API keys secure

2. **Network Security**:
   - Use HTTPS/WSS in production
   - Configure proper firewall rules
   - Consider using VPN for remote access

3. **File Permissions**:
   - Restrict access to sensitive directories
   - Use appropriate file permissions

## Support

For additional help:

1. Check the main [README.md](README.md) for general information
2. Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions
3. Review [DOCKER.md](DOCKER.md) for Docker-specific details
4. Check [USER_GUIDE.md](USER_GUIDE.md) for detailed configuration instructions
5. Open an issue on [GitHub](https://github.com/murtaza-nasir/maestro/issues) for bugs or feature requests

## Windows-Specific Notes

- **Line Endings**: Git for Windows handles line ending conversion automatically
- **Path Separators**: Use forward slashes (`/`) in configuration files
- **File Permissions**: Windows handles file permissions differently than Unix systems
- **Performance**: WSL 2 backend in Docker Desktop provides better performance than Hyper-V
- **Antivirus**: Some antivirus software may interfere with Docker operations; add exceptions if needed 