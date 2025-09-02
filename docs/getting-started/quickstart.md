# Quick Start

Get MAESTRO up and running in minutes with this streamlined installation guide.

## Prerequisites

Before you begin, ensure you have:

- **Docker** and **Docker Compose** (v2.0+) installed
- **Git** for cloning the repository
- **5-10 GB disk space** for AI models and database
- **API keys** for at least one AI provider (OpenAI, Anthropic, Groq, etc.)

## Quick Installation

### The Simplest Way to Get Started

```bash
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
./setup-env.sh    # Linux/macOS (interactive configuration wizard)
# or setup-env.ps1 # Windows PowerShell
docker compose up -d --build  # Build ensures latest changes
```

#### What the Setup Script Does

The `setup-env.sh` (or `setup-env.ps1` on Windows) is an interactive configuration wizard that:

1. **Creates your `.env` file** from the template (`.env.example`)

2. **Configures network access**:
    - **Simple mode** (default): localhost-only access for single-machine use
    - **Network mode**: Auto-detects your IP for access from other devices on your network
    - **Custom domain**: Configure for reverse proxy setups (nginx, Caddy, etc.)

3. **Sets the application port** (default: 80, customizable)

4. **Secures your installation**:
    - Generates cryptographically secure passwords for PostgreSQL database
    - Creates a strong admin password for the web interface
    - Generates a secure JWT secret key for authentication
    - Displays your admin credentials (save them!)

5. **Configures your timezone** for proper timestamps

6. **Provides startup instructions** specific to your configuration

!!! tip "Security Note"
    The script can automatically generate secure passwords (recommended) or let you set custom ones. Generated passwords are stored in your `.env` file and the admin password is displayed once - make sure to save it!

### First-Time Startup

!!! warning "Initial Model Download"
    First startup may take 5-10 minutes to download AI models. Monitor progress with:
    ```bash
    docker compose logs -f maestro-backend
    # Wait for: "MAESTRO Backend Started Successfully!"
    ```

## Platform-Specific Quick Start

### Linux/macOS

1. **Clone and run the setup wizard:**
    ```bash
    git clone https://github.com/murtaza-nasir/maestro.git
    cd maestro
    ./setup-env.sh  # Interactive configuration
    ```

2. **During setup, you'll be prompted for:**
    - **Network configuration** (3 options):
        - Simple (localhost only) - Press Enter to use default
        - Network - Script auto-detects your IP address
        - Custom domain - For nginx/Caddy reverse proxy setups
    - **Port number** - Default 80, or choose any available port
    - **Security setup** - Press 1 for automatic secure password generation
    - **Timezone** - Default America/Chicago, or enter your timezone

3. **Start MAESTRO:**
    ```bash
    ./start.sh  # Automatic GPU detection and startup
    # Or manually: docker compose up -d
    ```
    
    !!! info "GPU Support"
        The `start.sh` script automatically detects NVIDIA GPUs and uses the appropriate Docker Compose configuration

### Windows

1. **Clone and prepare:**
    ```powershell
    git clone https://github.com/murtaza-nasir/maestro.git
    cd maestro
    .\fix-line-endings.ps1  # Important: Fixes Unix/Windows line ending issues
    ```

2. **Run the configuration wizard:**
    ```powershell
    .\setup-env.ps1  # PowerShell (recommended)
    # Or: setup-env.bat  # Command Prompt
    ```
    
    The wizard will guide you through the same options as Linux/macOS:
    
    - Network access configuration
    - Port selection  
    - Automatic secure password generation
    - Timezone configuration

3. **Start MAESTRO:**
    ```powershell
    # Without GPU (most Windows users):
    docker compose -f docker-compose.cpu.yml up -d
    
    # With NVIDIA GPU and CUDA support:
    docker compose up -d
    ```
    
    !!! warning "Windows Line Endings"
        If you get a `/bin/bash^M: bad interpreter: No such file or directory` error, try running `.\fix-line-endings.ps1`.

## Access MAESTRO

Once startup is complete, access the web interface:

- **URL**: http://localhost (or the address shown by setup script)
- **Default Username**: `admin`
- **Default Password**: Generated during setup (check output or `.env` file)

!!! important "Security"
    If you used the setup script with automatic password generation, your admin password was displayed once during setup. If you missed it, check the `ADMIN_PASSWORD` field in your `.env` file.

### Reconfiguring Your Installation

If you need to change your configuration after initial setup:

1. **Quick reconfiguration** - Run setup script again:
    ```bash
    ./setup-env.sh  # Will prompt to overwrite existing .env
    ```

2. **Manual editing** - Edit the `.env` file directly:
    ```bash
    nano .env  # or your preferred editor
    docker compose down
    docker compose up -d
    ```

3. **Reset everything** (removes all data):
    ```bash
    docker compose down -v
    rm .env
    ./setup-env.sh
    docker compose up -d
    ```

## Verify Installation

Check that all services are running:

```bash
docker compose ps
```

You should see:

- `maestro-nginx` - Running (port 80)
- `maestro-frontend` - Running
- `maestro-backend` - Running
- `maestro-postgres` - Running (healthy)
- `maestro-doc-processor` - Running

## Quick Configuration

### Essential Settings

After logging in, configure these essential settings:

1. **AI Provider** (Settings → AI Config)
   - Select your provider (Openrouter, OpenAI, Custom: Any OpenAI compatible API endpoint, etc.)
   - Enter your API key (enter a random key if you are using a local llm without an API key)
   - Test the connection
   - Choose models for various agent types (if you're hosting just one locally, use this for all agent types)

2. **Search Provider** (Settings → Search)
   - Configure Tavily, LinkUp, Jina, or SearXNG
   - Enter API key if using web search (not needed for SearXNG)

3. **User Profile** (Settings → Profile)
   - Change default password
   - Update profile information

## Start Using MAESTRO

### Your First Research

1. **Upload Documents** (Optional)

    - Navigate to Documents tab
    - Create a document group
    - Drag and drop PDFs, Word files, Markdown files anywhere on screen
    - Document status shows processing progress
    - Wait for status to show "completed"
    - Upload times will vary: can take a long time if you are processing without a GPU

2. **Start a Chat**

    - Go to Research tab
    - Click "New Chat"
    - Select a document group (with relevant documents from last step) and/or turn on web search
    - Ask a question about the topic you would like to research
    - The agent will suggest some preliminary directions to investigate
    - Suggest changes to the questions
    - Suggest your tone/style/length requirements, source preferences, or other similar research parameters
    - Once ready, tell the agent to start the research job, or press the start button on the top right
    - Let MAESTRO conduct autonomous research
    - Monitor progress in the research tab

## Common Issues

### Login Fails on First Start

The backend is still downloading models and starting up. Wait 5-10 minutes and monitor:
```bash
docker compose logs -f maestro-backend
# Wait for: "MAESTRO Backend Started Successfully!"
```

### Port Already in Use

Change the port in your `.env` file:
```bash
FRONTEND_PORT=3030  # Change to available port
```

### GPU Not Detected

Ensure NVIDIA Container Toolkit is installed:
```bash
nvidia-smi  # Should show your GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

## Next Steps

- **[Detailed Installation Guide](installation/index.md)** - Platform-specific instructions
- **[Configuration Guide](configuration/overview.md)** - Advanced settings
- **[User Guide](../user-guide/index.md)** - Complete feature documentation
- **[Troubleshooting](../troubleshooting/index.md)** - Solutions to common problems

## Stop and Restart

To stop MAESTRO:
```bash
docker compose down
```

To restart:
```bash
docker compose up -d
```

To completely reset (removes all data):
```bash
docker compose down -v
```

## Getting Help

- Check the [FAQ](../troubleshooting/faq.md)
- Report issues on [GitHub](https://github.com/murtaza-nasir/maestro/issues)
- Review the [Troubleshooting Guide](../troubleshooting/index.md)