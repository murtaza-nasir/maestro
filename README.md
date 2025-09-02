<p align="center">
  <img src="images/logo.png" alt="MAESTRO Logo" width="200"/>
</p>

# MAESTRO: Your Self-Hosted AI Research Assistant

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Version](https://img.shields.io/badge/Version-0.1.5--alpha-green.svg)](https://github.com/murtaza-nasir/maestro.git)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://hub.docker.com/r/yourusername/maestro)
[![Documentation](https://img.shields.io/badge/Docs-Available-brightgreen.svg)](https://yourusername.github.io/maestro/)

> **Version 0.1.5-alpha (January 2025) - Major Update**
> 
> - **Performance**: Complete async backend migration (2-3x faster)
> - **Stability**: 50+ bug fixes and mission recovery improvements
> - **Documentation**: Complete overhaul with example reports and guides
> - **UI/UX**: Enhanced interface with LaTeX support and better navigation 

MAESTRO is an AI-powered research platform you can host on your own hardware. It's designed to manage complex research tasks from start to finish in a collaborative research environment. Plan your research, let AI agents carry it out, and watch as they generate detailed reports based on your documents and sources from the web.

## 📚 Documentation

**[View Full Documentation](https://yourusername.github.io/maestro/)**

- **[Quick Start](https://yourusername.github.io/maestro/getting-started/quickstart/)** - Get up and running in minutes
- **[Installation](https://yourusername.github.io/maestro/getting-started/installation/)** - Platform-specific setup
- **[Configuration](https://yourusername.github.io/maestro/getting-started/configuration/overview/)** - AI providers and settings
- **[User Guide](https://yourusername.github.io/maestro/user-guide/)** - Complete feature guide
- **[Example Reports](https://yourusername.github.io/maestro/example-reports/)** - Sample outputs from various models
- **[Troubleshooting](https://yourusername.github.io/maestro/troubleshooting/)** - Common issues and solutions

## 🚀 Getting Started

### Prerequisites
- Docker and Docker Compose (v2.0+)
- 16GB RAM minimum (32GB recommended)
- 30GB free disk space
- API keys for at least one AI provider

### Quick Start

```bash
# Clone and setup
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
./setup-env.sh    # Linux/macOS
# or
.\setup-env.ps1   # Windows PowerShell

# Start services
docker compose up -d

# Monitor startup (takes 5-10 minutes first time)
docker compose logs -f maestro-backend
```

Access at **http://localhost** • Default: `admin` / `admin123`

For detailed installation instructions, see the [Installation Guide](https://yourusername.github.io/maestro/getting-started/installation/).

## 🔧 Configuration

- **CPU Mode**: Use `docker compose -f docker-compose.cpu.yml up -d`
- **GPU Support**: Automatic detection on Linux/Windows with NVIDIA GPUs
- **Network Access**: Configure via setup script options

For troubleshooting and advanced configuration, see the [documentation](https://yourusername.github.io/maestro/).

## 🛠️ Core Features

- **Multi-Agent Research System**: Planning, Research, Reflection, and Writing agents working in concert
- **Advanced RAG Pipeline**: Dual BGE-M3 embeddings with PostgreSQL + pgvector
- **Document Management**: PDF, Word, and Markdown support with semantic search
- **Web Integration**: Multiple search providers (Tavily, LinkUp, Jina, SearXNG)
- **Self-Hosted**: Complete control over your data and infrastructure
- **Local LLM Support**: OpenAI-compatible API for running your own models

## License

This project is **dual-licensed**:

1.  **GNU Affero General Public License v3.0 (AGPLv3)**: MAESTRO is offered under the AGPLv3 as its open-source license.
2.  **Commercial License**: For users or organizations who cannot comply with the AGPLv3, a separate commercial license is available. Please contact the maintainers for more details.

## Contributing

Feedback, bug reports, and feature suggestions are highly valuable. Please feel free to open an Issue on the GitHub repository.
