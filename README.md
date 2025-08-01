<p align="center">
  <img src="images/logo.png" alt="MAESTRO Logo" width="200"/>
</p>

# MAESTRO: Your Self-Hosted AI Research Assistant

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

MAESTRO is an AI-powered research platform you can host on your own hardware. It's designed to manage complex research tasks from start to finish in a collaborative, multi-user environment. Plan your research, let AI agents carry it out, and watch as they generate detailed reports based on your documents and sources from the web.

<p align="center">
  <img src="images/10-research-draft.png" alt="Final Draft" width="700"/>
</p>

## A New Way to Conduct Research

MAESTRO streamlines the research process with a unified, chat-driven workflow. Define your research goals, upload your source materials, and let a team of AI agents handle the heavy lifting. It's a powerful tool for anyone who works with large amounts of information, from academics and analysts to writers and developers.

### Core Features

<details>
  <summary><strong>Manage Your Document Library</strong></summary>
  <br>
  <p>Upload and manage your PDF documents in a central library. MAESTRO's advanced Retrieval-Augmented Generation (RAG) pipeline is optimized for academic and technical papers, ensuring your AI agents have access to the right information.</p>
  <p align="center">
    <img src="images/01-document-library.png" alt="Document Library" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Create Focused Document Groups</strong></summary>
  <br>
  <p>Organize your library by creating document groups for specific projects. This allows you to direct the AI to pull information from a curated set of sources, ensuring relevance and accuracy in its research.</p>
  <p align="center">
    <img src="images/02-document-groups.png" alt="Document Groups" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Customize Your Research Mission</strong></summary>
  <br>
  <p>Fine-tune the research process by setting specific parameters for the mission. You can define the scope, depth, and focus of the AI's investigation to match your exact needs.</p>
  <p align="center">
    <img src="images/03-mission-settings.png" alt="Mission Settings" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Chat with Your Documents and the Web</strong></summary>
  <br>
  <p>Use the chat interface to ask questions and get answers sourced directly from your documents or the internet. It's a powerful way to get quick insights or inspiration for your work.</p>
  <p align="center">
    <img src="images/04-chat-with-docs.png" alt="Chat with Documents" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Get Help from the Writing Assistant</strong></summary>
  <br>
  <p>The writing assistant works alongside you, ready to pull information from your library or the web to help you draft notes, summarize findings, or overcome writer's block.</p>
  <p align="center">
    <img src="images/05-writing-assistant.png" alt="Writing Assistant" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Follow the Agent's Research Path</strong></summary>
  <br>
  <p>MAESTRO provides full transparency into the AI's process. You can see the research outline it develops and follow along as it explores different avenues of investigation.</p>
  <p align="center">
    <img src="images/06-research-transparency.png" alt="Research Transparency" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Review AI-Generated Notes</strong></summary>
  <br>
  <p>Let the research agent dive into your PDF collection or find new sources online. It will then synthesize the information and generate structured notes based on your research questions.</p>
  <p align="center">
    <img src="images/07-automated-notes.png" alt="Automated Notes" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Track Mission Progress in Detail</strong></summary>
  <br>
  <p>Keep a close eye on every step of the research mission. The system provides detailed, real-time tracking of agent activities and status updates.</p>
  <p align="center">
    <img src="images/08-mission-tracking.png" alt="Mission Tracking" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Understand the Agent's Reasoning</strong></summary>
  <br>
  <p>The AI agents provide detailed reflection notes, giving you insight into their thought processes, the decisions they make, and the conclusions they draw from the data.</p>
  <p align="center">
    <img src="images/09-agent-reflection.png" alt="Agent Reflection" width="700"/>
  </p>
</details>

<details>
  <summary><strong>Get a Full Report with References</strong></summary>
  <br>
  <p>Based on the research plan and generated notes, a final draft will be generated, including references from your documents and internet sources.</p>
</details>

<details>
  <summary><h2>How It Works: The WRITER Agentic Framework</h2></summary>
  <br>

MAESTRO is a sophisticated multi-agent system designed to automate complex research synthesis. Instead of a single AI model, MAESTRO employs a team of specialized AI agents that collaborate to plan, execute, critique, and write research reports.

This methodology ensures a structured, transparent, and rigorous process from the initial question to the final, evidence-based report.

<p align="center">
  <em>The MAESTRO Research Lifecycle</em>
</p>
<p align="center">

```mermaid
graph TD
    subgraph User Interaction
        A["User Defines Mission"]
    end

    subgraph "Phase 1: Planning"
        B["Planning Agent<br>Creates Research Plan & Outline"]
    end

    subgraph "Phase 2: Research & Reflection"
        C["Research Agent<br>Gathers Information (RAG/Web)"]
        D["Reflection Agent<br>Critiques Findings & Identifies Gaps"]
        C --> D
        D -- "Revisions Needed? ↪" --> B
        D -- "Evidence Complete? ✔" --> E
    end

    subgraph "Phase 3: Writing & Reflection"
        E["Writing Agent<br>Drafts Report Sections"]
        F["Reflection Agent<br>Reviews Draft for Clarity"]
        E --> F
        F -- "Revisions Needed? ↪" --> E
        F -- "Draft Approved? ✔" --> G
    end

    subgraph "Phase 4: Finalization"
        G["Agent Controller<br>Composes Final Report"]
    end

    A --> B
    B --> C
    G --> H["User Receives Report"]

    style A fill:#e6e6fa,stroke:#333,stroke-width:1px
    style H fill:#e6e6fa,stroke:#333,stroke-width:1px
    style B fill:#f9f0ff,stroke:#333,stroke-width:2px
    style C fill:#e0f7fa,stroke:#333,stroke-width:2px
    style D fill:#fff0f5,stroke:#333,stroke-width:2px
    style E fill:#e8f5e9,stroke:#333,stroke-width:2px
    style F fill:#fff0f5,stroke:#333,stroke-width:2px
    style G fill:#fffde7,stroke:#333,stroke-width:2px
```
</p>

### The Core Agent Team

MAESTRO's capabilities are driven by a team of specialized agents, each with a distinct role:

*   **Agent Controller (The Orchestrator):** Manages the entire mission, delegating tasks to the appropriate agents and ensuring the workflow progresses smoothly from one phase to the next.
*   **Planning Agent (The Strategist):** Takes the user's initial request and transforms it into a structured, hierarchical research plan and a report outline. This creates a clear roadmap for the mission.
*   **Research Agent (The Investigator):** Executes the research plan by gathering information. It uses its tools—the local RAG pipeline and web search—to find relevant evidence and organizes it into structured `ResearchNote` objects.
*   **Reflection Agent (The Critical Reviewer):** This is the key to MAESTRO's analytical depth. The Reflection Agent constantly reviews the work of other agents, identifying knowledge gaps, inconsistencies, or deviations from the plan. Its feedback drives the iterative loops that refine and improve the quality of the research.
*   **Writing Agent (The Synthesizer):** Takes the curated research notes and weaves them into a coherent, well-structured narrative that follows the report outline.

### The Research Process: Iteration and Refinement

The research process is not linear; it's a series of iterative loops designed to simulate critical thinking and ensure a high-quality outcome.

1.  **The Research-Reflection Loop:**
    The `Research Agent` doesn't just gather information in one pass. After an initial round of research, the `Reflection Agent` steps in to critique the findings. It asks questions like:
    *   *Are there gaps in the evidence?*
    *   *Do sources contradict each other?*
    *   *Have new, unexpected themes emerged?*
    Based on this critique, the `Reflection Agent` can recommend new research tasks or even prompt the `Planning Agent` to revise the entire plan. This loop continues until the evidence is comprehensive and robust. The number of iterations is dynamic and depends on the complexity of the topic.

2.  **The Writing-Reflection Loop:**
    Drafting is also an iterative process. Once the `Writing Agent` produces a section of the report, the `Reflection Agent` reviews it for:
    *   **Clarity and Coherence:** Is the argument easy to follow?
    *   **Logical Flow:** Are the ideas connected logically?
    *   **Fidelity to Sources:** Does the writing accurately represent the evidence in the `ResearchNote`s?
    The `Writing Agent` then revises the draft based on this feedback. This loop repeats until the writing meets the required standard of quality and accuracy.

This structured, reflective, and iterative process allows MAESTRO to move beyond simple information aggregation and produce sophisticated, reliable, and auditable research syntheses.
</details>

## Getting Started

MAESTRO is designed to be run as a containerized application using Docker.

### Prerequisites
*   **Docker** and **Docker Compose**
*   **Git** for cloning the repository
*   **NVIDIA GPU** (recommended for optimal performance)
*   **Disk Space**: ~5GB for AI models (downloaded automatically on first run)

### Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/murtaza-nasir/maestro.git
    cd maestro
    ```

2.  **Configure Your Environment**
    Run the interactive setup script for a guided configuration:
    ```bash
    ./setup-env.sh
    ```
    This will help you set up network settings, API keys, and other essential parameters by creating a `.env` file for you.

3.  **Build and Run**
    Use Docker Compose to build the images and start the services in the background.
    ```bash
    docker compose up --build -d
    ```

4.  **Access MAESTRO**
    Once the containers are running, access the web interface at the address you configured (e.g., `http://localhost:3030`). The first-time login credentials are `admin` / `adminpass123`. It is highly recommended that you change this password immediately.

## Technical Overview

MAESTRO is built on a modern, decoupled architecture:

*   **Backend**: A robust API built with **FastAPI** that handles user authentication, mission control, agentic logic, and the RAG pipeline.
*   **Frontend**: A dynamic and responsive single-page application built with **React**, **Vite**, and **TypeScript**, using **Tailwind CSS** for styling.
*   **Real-time Communication**: **WebSockets** stream live updates, logs, and status changes from the backend to the frontend.
*   **Database**: **SQLAlchemy** and **SQLite** are used for database management.
*   **Containerization**: **Docker Compose** orchestrates the multi-service application for reliable deployment.

### Fully Self-Hosted Operation

MAESTRO can be configured for a completely self-hosted environment. It supports local, OpenAI-compatible API models, allowing you to run your own LLMs. For web searches, it integrates with **SearXNG**, a private and hackable metasearch engine, ensuring that your entire research workflow can remain on your own hardware.

For advanced users and administrators, a powerful **Command Line Interface (CLI)** is available for bulk document ingestion, user management, and other administrative tasks. For more details, see [DOCKER.md](./DOCKER.md).

## License

This project is **dual-licensed**:

1.  **GNU Affero General Public License v3.0 (AGPLv3)**: MAESTRO is offered under the AGPLv3 as its open-source license.
2.  **Commercial License**: For users or organizations who cannot comply with the AGPLv3, a separate commercial license is available. Please contact the maintainers for more details.

## Contributing

Feedback, bug reports, and feature suggestions are highly valuable. Please feel free to open an Issue on the GitHub repository.
