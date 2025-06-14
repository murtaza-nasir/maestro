# MAESTRO: Multi-Agent Execution System & Tool-driven Research Orchestrator

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

This project is dual-licensed. See the [License](#license) section for details.

MAESTRO is a self-hosted AI-powered research application designed to streamline complex research tasks. It features a modular framework built around document ingestion, Retrieval-Augmented Generation (RAG), and multi-step agentic execution. Whether you prefer a rich web interface or a powerful command-line tool, MAESTRO offers robust capabilities to plan, execute, and report on your research missions with transparency and control.

[![MAESTRO Intro](https://img.youtube.com/vi/nIU29KRjkzU/0.jpg)](https://youtu.be/nIU29KRjkzU)

##  Key Highlights

* **Local Deep Research:** Set up locally and get comprehensive deep-research reports on your own document collection as well as online sources using your choice of local or API-based LLMs.
* **Intuitive Research Management:** Interact via the **MAESTRO Streamlit Web UI** for a chat-like experience with real-time progress, or leverage the comprehensive **Command-Line Interface (CLI)** for batch processing and automation.
* **Sophisticated AI Collaboration:** A multi-agent system (Planning, Research, Reflection, Writing) works in concert to break down complex questions, gather information, analyze findings, and synthesize coherent reports.
* **Powerful RAG Pipeline:** Ingest PDFs into a queryable knowledge base. MAESTRO converts documents to Markdown, extracts metadata, performs intelligent chunking, and uses hybrid search (dense + sparse embeddings) with optional reranking for precise information retrieval.
* **Transparent Cost Control:** Keep your budget in check with real-time monitoring of API usage costs, token consumption (per model), and web search calls. Cost statistics are automatically embedded in generated reports.
* **Flexible & Configurable:** Tailor the research process to your needs. Configure LLM providers (OpenRouter, local), select specific models for different agent roles, customize search sources (local documents, web, or both), and adjust research depth and iterations.
* **Automated Reporting:** Automatically generate detailed Markdown research reports, complete with citations, embedded cost breakdowns, and model usage information.

##  Getting Started

### Prerequisites
* Python 3.x
* Git
* NVIDIA-Cuda-compatible GPU (required for optimal performance of the Embedder and Reranker)

### Choose your installation method:

#### Local Installation

1.  Clone the Repository
    ```bash
    git clone https://github.com/murtaza-nasir/maestro.git
    cd maestro # Or your project directory name
    ```

2.  Set Up a Virtual Environment (Recommended)

    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    ```

3.  Install Dependencies

    ```bash
    pip install -r ai_researcher/requirements.txt
    ```

    *Note: For GPU support, `torch` installation may require specific commands. Please refer to the [PyTorch installation guide](https://pytorch.org/get-started/locally/).*

4.  Configure Environment Variables

    Create a `.env` file within the `ai_researcher` directory. You can copy the provided template:

    ```bash
    cp ai_researcher/.env.example ai_researcher/.env
    ```

    Then, edit `ai_researcher/.env` to add your API keys and customize settings. 

5.  Run the Application

    ```bash
    python -m streamlit run ai_researcher/ui/app.py
    ```

    This will start the Streamlit web interface, accessible at http://localhost:8501

#### Docker Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/murtaza-nasir/maestro.git
    cd maestro # Or your project directory name
    ```

2.  Configure Environment Variables

    Create a `.env` file within the `ai_researcher` directory. You can copy the provided template:

    ```bash
    cp ai_researcher/.env.example ai_researcher/.env
    ```

    Then, edit `ai_researcher/.env` to add your API keys and customize settings.
      
3.  Build the Docker image:
    ```bash
    docker compose build -t maestro .
    ```

4.  Run the Docker container:
    ```bash
    docker compose up
    ```

    This will start the Streamlit web interface, accessible at http://localhost:8501

    For more detailed instructions, see the [DOCKER.md](./DOCKER.md) file.

Key configuration options (see `ai_researcher/.env.example` for all settings):

  * **LLM Providers:** `FAST_LLM_PROVIDER`, `MID_LLM_PROVIDER`, `INTELLIGENT_LLM_PROVIDER` (can be `"openrouter"` or `"local"`).
  * **Web Search:** `WEB_SEARCH_PROVIDER` (can be `"tavily"` or `"linkup"`).
  * **API Keys:** `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `LINKUP_API_KEY` (depending on your choices).
  * **Local LLM Setup:** `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_FAST_MODEL`, `LOCAL_LLM_MID_MODEL`, `LOCAL_LLM_INTELLIGENT_MODEL` (if using a local LLM).
  * **OpenRouter:** `OPENROUTER_FAST_MODEL`, `OPENROUTER_MID_MODEL`, `OPENROUTER_INTELLIGENT_MODEL` (if using OpenRouter).

##  Configuration Deep Dive

MAESTRO offers extensive customization through environment variables in `ai_researcher/.env`.

### LLM Configuration

  * **Provider Selection:** Assign different LLM providers for various task complexities:
      * `FAST_LLM_PROVIDER`: For 'light' tasks like planning and reflection.
      * `MID_LLM_PROVIDER`: For 'mid' tasks such as research and writing.
      * `INTELLIGENT_LLM_PROVIDER`: For highly complex reasoning (if needed).
  * **OpenRouter Models:** If using OpenRouter, specify models (e.g., `OPENROUTER_FAST_MODEL="openai/gpt-4o-mini"`, `OPENROUTER_MID_MODEL="openai/gpt-4o"`) and provide your `OPENROUTER_API_KEY`.
  * **Local Models:** If using a local LLM, set `LOCAL_LLM_BASE_URL` (e.g., `"http://127.0.0.1:5000/v1/"`), `LOCAL_LLM_API_KEY` (often `"none"`), and the corresponding model IDs (e.g., `LOCAL_LLM_FAST_MODEL`).
  * **Connection Settings:** Customize `MAX_RETRIES` for LLM calls, `RETRY_DELAY`, and `LLM_REQUEST_TIMEOUT`.

### Web Search Configuration

  * **Provider:** Choose your web search provider via `WEB_SEARCH_PROVIDER` (`"tavily"` or `"linkup"`).
  * **API Keys:** Supply the relevant API key (`TAVILY_API_KEY` or `LINKUP_API_KEY`).
  * **Cost & Caching:** Set `WEB_SEARCH_COST_PER_CALL` for accurate cost tracking and `WEB_CACHE_EXPIRATION_DAYS` to optimize repeat webpage retrievals.

### Research Process Parameters

Fine-tune the agentic research workflow:

  * `STRUCTURED_RESEARCH_ROUNDS`: Number of iterative research passes.
  * `MAX_TOTAL_DEPTH`, `MAX_DEPTH_PASS1`: Control the depth of the research outline.
  * `MAX_REFINEMENT_ITERATIONS`: Limit research cycles per section.
  * `THOUGHT_PAD_CONTEXT_LIMIT`: Number of recent thoughts maintained for agent context.
  * Search result counts for different phases (e.g., `INITIAL_EXPLORATION_DOC_RESULTS`, `MAIN_RESEARCH_WEB_RESULTS`).

*(For a comprehensive list of all environment variables and their default values, please consult the `ai_researcher/.env.example` file.)*

**Configuration Example: Hybrid Setup (Local for Light tasks, OpenRouter for Mid/Intelligent, LinkUp Search)**

```dotenv
FAST_LLM_PROVIDER=local
MID_LLM_PROVIDER=openrouter
INTELLIGENT_LLM_PROVIDER=openrouter # Assuming you also have an INTELLIGENT_LLM_PROVIDER setting
WEB_SEARCH_PROVIDER=linkup

LINKUP_API_KEY=your_linkup_key

# --- Local LLM Details ---
LOCAL_LLM_BASE_URL=http://127.0.0.1:5000/v1/)
LOCAL_LLM_API_KEY=none
LOCAL_LLM_FAST_MODEL=your-local-light-model-id # Replace

# --- OpenRouter Details ---
OPENROUTER_API_KEY=your_openrouter_key
# OPENROUTER_MID_MODEL=openai/gpt-4o # Optional override
# OPENROUTER_INTELLIGENT_MODEL=google/gemma-3-27b-it # Optional override
```

##  Usage

Ensure your virtual environment is activated and run all commands from the project root directory (`researcher2`).

### 1\. Document Ingestion

Build your local knowledge base by processing PDF documents. This involves PDF-to-Markdown conversion (`marker` library), metadata extraction (using `pymupdf` and an LLM), text chunking, generation of dense (`BAAI/bge-m3`) and sparse embeddings, and storage in ChromaDB.

1.  Place your PDF files into the `ai_researcher/data/raw_pdfs` directory.
2.  Run the ingestion command:
    ```bash
    python -m ai_researcher.main_cli ingest
    ```
      * The system tracks processed files in an SQLite database (`ai_researcher/data/processed/metadata.db`) to avoid redundant work.
      * For options like specifying different directories or forcing re-embedding, use `python -m ai_researcher.main_cli ingest --help`.

### 2\. Command-Line Interface (CLI)

The CLI provides tools for direct interaction and non-interactive research missions.

#### Basic RAG Queries

Perform direct Retrieval-Augmented Generation queries against your ingested document store:

```bash
python -m ai_researcher.main_cli query "Your query about the ingested documents"
```

  * Use `python -m ai_researcher.main_cli query --help` for options like number of results (`-k`), filtering (`--filter-doc-id`), or disabling reranking (`--no-rerank`).

#### Inspecting the Vector Store

Check the contents and statistics of your document vector store:

```bash
python -m ai_researcher.main_cli inspect-store --list-docs
```

  * Use `python -m ai_researcher.main_cli inspect-store --help` for more options.

#### Running Full Research via CLI (Non-Interactive)

Execute the complete research process (planning, research, writing, citation) without user interaction. Final reports are saved as Markdown files.

  * **Single Question:**
    ```bash
    python -m ai_researcher.main_cli run-research --question "Your research question here" --output-dir path/to/save/reports
    ```
  * **Multiple Questions from File:** Create a text file (e.g., `questions.txt`) with one research question per line.
    ```bash
    python -m ai_researcher.main_cli run-research --input-file path/to/questions.txt --output-dir path/to/save/reports
    ```
  * **Search Configuration Options:**
      * `--no-use-web-search`: Use only local RAG (disables web search).
      * `--no-use-local-rag`: Use only web search (disables local RAG).
      * (Default behavior uses both local RAG and web search).
  * See `python -m ai_researcher.main_cli run-research --help` for all options, including output directory, model selection, and vector store paths.

### 3\. MAESTRO Streamlit Web UI

Launch the interactive web interface for a guided research experience:

```bash
python -m streamlit run ai_researcher/ui/app.py
```

The MAESTRO UI offers:

  * **Chat-Based Interface:** Enter your research goal and refine questions through natural conversation.
  * **Mission Control:** Start/stop research missions, configure research sources (local, web, or both), and view real-time status.
  * **Cost and Resource Monitoring:** Track estimated API costs, token usage, and web search calls live.
  * **Research Visualization:** Observe the research outline develop, track agent activities with status indicators, and explore detailed, expandable execution logs.
  * **Report Management:** View final research reports directly in the UI and download them as Markdown files, complete with embedded cost statistics.

##  Crafting Effective Prompts & Usage Tips

To get the best results from MAESTRO, whether interacting via the CLI or the Streamlit UI, consider the following tips when formulating your research requests:

### Be Specific and Detailed in Your Core Question

The more context you provide, the better MAESTRO can understand your needs and generate a targeted, relevant output. Don't just ask a general question; include:

  * **Core Question:** Clearly state the main information you are seeking.
  * **Important Aspects/Qualifiers:** Specify any particular angles, sub-topics, timeframes, geographical locations, or specific entities (people, organizations, technologies) you want the research to focus on or exclude.
  * **Scope:** Define the breadth and depth. Are you looking for a broad overview or a deep dive into a niche area?

If the above aspects are not defined clearly, the agents will default to writing a detailed academic report with a broad scope.

### Define Your Desired Output

Help the research agents understand the kind of report or information you expect:

  * **Report Format:** Do you need a summary, a comparative analysis, a literature review, a pros and cons list, a historical overview, or something else? While MAESTRO primarily generates Markdown reports, specifying the *structure* of the content is key.
  * **Intended Audience:** Who is this research for? Technical experts, general public, business executives, students? This influences the language, complexity, and depth.
  * **Tone:** Should the report be formal, informal, academic, critical, neutral, persuasive?
  * **Length:** LLMs are not good at keeping count of words. Provide an approximate desired length in terms of sections, as the main research loop is section based. This helps the agents manage the scope of information gathering and synthesis.
  * **Key Information to Include/Exclude:** If there are specific data points, theories, arguments, or counter-arguments you definitely want to see (or avoid), mention them.

### Interacting with the MAESTRO UI Messenger Agent

When using the Streamlit UI, the initial chat interface allows for refinement of your research mission before full execution:

  * **Iterative Refinement:** You can ask the messenger agent to revise the generated research questions, change some of them, adjust the scope, or clarify aspects of the research plan.
  * **Focus on One Adjustment at a Time:** For clearer communication and more predictable results, it's best to ask for one type of revision or clarification per message (e.g., "Can you rephrase question 3 to focus more on X?" rather than "Change question 3, add a question about Y, and make the tone more academic.").
  * **Specify Output Characteristics:** Even at this stage, you can reiterate or refine your expectations for tone, length, and audience for the final report.

### Example Prompts

Below are examples illustrating how to construct detailed prompts.

  * *Example 1: Basic Prompt*
    ```
    What are the effects of climate change? 
    ```
    This prompt will get you a very broad report. The focus of the report will develop based on the research materials MAESTRO finds.
  * *Example 2: Detailed and Specific Prompt for MAESTRO*
    ```
    What are the primary economic impacts of rising sea levels on coastal communities in Southeast Asia over the next 20 years? Focus on impacts to infrastructure, tourism, and agriculture. Exclude analysis of mitigation strategies for now. This is intended for policymakers with a general understanding of climate science but not necessarily economics.
    ```
  * *Example 3: UI Interaction Snippet (revise research questions)*

    *User to MAESTRO UI after initial plan:*
    ```
    The outline looks good, but can you ensure that for the section on 'Agricultural Impacts,' we specifically look into saltwater intrusion effects on rice cultivation? 
    ```
  * *Example 4: UI Interaction Snippet (Illustrative)*

    *User to MAESTRO UI after initial plan:*
    ```
    Lets make this an executive summary with a maximum of 4 sections and no subsections. 
    ```
  * *Example 5: Detailed and Specific Prompt with style and length*

    ```
    What governance mechanisms can address the tension between algorithmic efficiency and procedural justice in automated decision systems within public sector contexts, while maintaining democratic accountability and citizen trust? Keep it short and intended for an academic audience with a background in decision science.   
    ```
  * *Example 6: Define the style*

    *Add as part of your main prompt or while interacting with messenger agent:*
    ```
    Write in a fantasy novel style.
    ```

The same rules above will apply to prompts saved to file and batch-processed via the CLI.

##  Core Architecture & Features

MAESTRO's power comes from its sophisticated underlying architecture.

### Multi-Agent Collaboration System

Research is conducted by a team of specialized AI agents that collaborate dynamically:

  * **Planning Agent:** Creates the initial research outline and structures the investigation.
  * **Research Agent:** Gathers information by querying local documents (via RAG) and performing web searches.
  * **Reflection Agent:** Analyzes the quality of research findings, identifies knowledge gaps, and proposes follow-up questions or areas for deeper investigation.
  * **Writing Agent:** Synthesizes all gathered and refined information into coherent, well-structured reports with automatic citation and reference management.

This system supports an **iterative research process**, allowing for multiple research passes with reflection and refinement, ensuring comprehensive coverage and progressive deepening of insights.

### Advanced RAG Pipeline

The Retrieval-Augmented Generation pipeline is key to leveraging your local document store:

  * **PDF Ingestion:** High-quality PDF to Markdown conversion using the `marker` library for superior text extraction.
  * **Metadata Extraction:** Employs `pymupdf` and an LLM to capture structured metadata such as title, authors, and publication details.
  * **Intelligent Chunking:** Splits Markdown into overlapping, paragraph-based chunks with configurable size and overlap for optimal context.
  * **Hybrid Embeddings:** Generates both dense (`BAAI/bge-m3`) and sparse embeddings for more nuanced and effective semantic search.
  * **Vector Storage:** Utilizes ChromaDB for persistent and efficient storage of embeddings and metadata.
  * **Hybrid Retrieval:** Combines dense and sparse vector search with configurable weights to balance different retrieval strengths.
  * **Reranking:** Optionally improves search result relevance using `BAAI/bge-reranker-v2-m3`.
  * **Processed File Tracking:** An SQLite database prevents redundant processing of previously ingested documents.

### Comprehensive Cost Tracking & Resource Monitoring

MAESTRO provides detailed insights into operational expenses:

  * **Real-time Cost Calculation:** Automatically tracks API costs based on token usage (with per-model rates) and web search calls (configurable cost-per-call).
  * **Token Usage Monitoring:** Logs prompt and completion tokens for each LLM call, providing aggregated and model-specific statistics.
  * **Embedded Reporting:** Cost statistics, including breakdowns by model type and web search usage, are embedded directly into generated research reports for easy budget tracking and analysis.
  * **Cost Optimization Features:**
      * Select cost-effective models for different agent roles.
      * Optionally disable web search to reduce API calls.
      * Control research depth and breadth to manage overall token consumption.

### Other Notable Features

  * **Question Refinement:** Interactively refine research questions before execution, with AI assistance for generating questions based on your initial goal.
  * **Structured Report Generation:** Produces well-organized reports with hierarchical sections, achieved through multiple writing passes for content refinement.
  * **Model Flexibility & Fallbacks:** Seamlessly switch between OpenRouter and local LLM providers. The system includes automatic retries and error handling for API failures.
  * **Context Management:** A "Thought Pad" maintains context between agent calls (configurable history length), and the mission state (logs, artifacts) is persisted.
  * **Tool Registry:** Manages various tools available to agents. Currently only supports document search and web search.

I'll help you modify the text with the more accurate information from the document. Here's the updated "Recommended Models for Agent Roles" section:

# Recommended Models for Agent Roles

Selecting the right Large Language Models (LLMs) for MAESTRO's different agent roles is crucial for achieving high-quality, factually accurate research outputs. Based on [our comprehensive evaluation of factual accuracy](./VERIFIER_AND_MODEL_FINDINGS.md) in research and writing tasks, we recommend the following models for MAESTRO's agent roles:

### Planning Agent (`FAST_LLM_PROVIDER`):
This role needs to efficiently structure tasks and produce outlines.
* **Top API Choice:** `openai/gpt-4o-mini` offers a good balance of capability and cost for planning tasks
* **Self-Hosted Recommendation:** `qwen/qwen3-8b` shows good performance for its size and provides reasonable speed for planning tasks
* **Alternative API Choice:** Smaller Qwen models like `qwen/qwen3-14b` (via API) are also effective options

### Research Agent & Writing Agent (`MID_LLM_PROVIDER`):
These roles require strong comprehension, synthesis and generation with good factual grounding.
* **Top Tier API Choices:**
  * **Qwen Family:** `qwen/qwen3-14b`, `qwen/qwen3-30b-a3b`, and `qwen/qwen-2.5-72b-instruct` demonstrated excellent aggregated performance
* **Strong Alternative API Choices:**
  * **Google Models:** `google/gemini-2.5-flash-preview` and `google/gemma-3-27b-it` excel particularly in accurate note generation
  * `anthropic/claude-3.7-sonnet` performs consistently well in both note-taking and writing
* **Self-Hosted Recommendations:**
  * `qwen/qwen3-14b` (highest overall aggregated score in testing)
  * `google/gemma-3-27b-it` (particularly strong for note generation)
  * `qwen/qwen3-30b-a3b` (strong overall performer)
* **Strategic Mix:** Consider using models like `google/gemini-2.5-flash-preview` or `google/gemma-3-27b-it` for Research Agent (stronger note-taking) and `qwen/qwen3-14b` for Writing Agent (stronger writing performance)

### Reflection Agent (`INTELLIGENT_LLM_PROVIDER` or capable `MID_LLM_PROVIDER`):
This critical role evaluates information quality, identifies knowledge gaps, and suggests refinements.
* **Top API Choices:**
  * **Verifier Panel Models:** `qwen/qwen3-30b-a3b`, `anthropic/claude-3.7-sonnet`, `meta-llama/llama-4-maverick` (selected for strong assessment capabilities)
  * **High-Performing Alternatives:** `google/gemini-2.5-flash-preview` and `qwen/qwen3-8b` showed strong verifier selection performance
* **Self-Hosted Recommendations:**
  * `qwen/qwen3-30b-a3b` (verifier panel member with strong research/writing performance)
  * `meta-llama/llama-4-maverick` (verifier panel member)
  * Larger Qwen models (e.g., `qwen/qwen-2.5-72b-instruct`)
  * `google/gemma-3-27b-it` (good self-hosted option when larger models aren't feasible)

**Important Considerations:**

  * **Provider and Availability:** Model availability varies between LLM providers (OpenRouter, local).
  * **Cost:** More capable models generally incur higher API costs. MAESTRO's cost tracking features help monitor this.
  * **Factuality vs. Fluency:** Our detailed findings ([VERIFIER\_AND\_MODEL\_FINDINGS.md](./VERIFIER_AND_MODEL_FINDINGS.md)) explore the nuances of how different models perform in maintaining factual consistency during complex research tasks. We recommend reviewing these findings when making your final model selections, especially for roles heavily involved in information synthesis and claim generation.
  * **Configuration:** Remember to set your chosen models in the `ai_researcher/.env` file using variables like `OPENROUTER_FAST_MODEL`, `LOCAL_MID_LLM_MODEL`, etc.

We are continuously evaluating models, and these recommendations will be updated as new models emerge and further testing is conducted. For a deeper dive into our evaluation methodology and specific model performance on factuality benchmarks, please refer to [VERIFIER\_AND\_MODEL\_FINDINGS.md](./VERIFIER_AND_MODEL_FINDINGS.md).

##  Important Notes

  * **Web Search API Keys:** Remember to set `WEB_SEARCH_PROVIDER` in your `.env` file and provide the corresponding `TAVILY_API_KEY` or `LINKUP_API_KEY`.
  * **Streamlit UI Synchronicity:** The Streamlit UI currently executes the entire research mission synchronously after the initial planning phase.

## Troubleshooting

If you encounter errors, especially with reflection outputs, it may be due to the LLM you are using. Certain LLMs, especially those that are not good with structured output generation, can cause errors. For example, `gemini-2.5-flash-preview` can sometimes fail to generate reflection outputs properly. If you encounter this issue, try using a different LLM.

## License

This project is **dual-licensed**:

1.  **GNU Affero General Public License v3.0 (AGPLv3)**
    [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

    MAESTRO is offered under the AGPLv3 as its open-source license. You are free to use, modify, and distribute this software under the terms of the AGPLv3. A key condition of the AGPLv3 is that if you run a modified version on a network server and provide access to it for others, you must also make the source code of your modified version available to those users under the AGPLv3.

    * You **must** create a file named `LICENSE` (or `COPYING`) in the root of your repository and paste the full text of the [GNU AGPLv3 license](https://www.gnu.org/licenses/agpl-3.0.txt) into it.
    * Read the full license text carefully to understand your rights and obligations.

2.  **Commercial License**

    For users or organizations who cannot or do not wish to comply with the terms of the AGPLv3 (for example, if you want to integrate MAESTRO into a proprietary commercial product or service without being obligated to share your modifications under AGPLv3), a separate commercial license is available.

    Please contact **Maestro Maintainers** for details on obtaining a commercial license.

**You must choose one of these licenses** under which to use, modify, or distribute this software. If you are using or distributing the software without a commercial license agreement, you must adhere to the terms of the AGPLv3.

## Contributing

While direct code contributions are not the primary focus at this stage, feedback, bug reports, and feature suggestions are highly valuable! Please feel free to open an Issue on the GitHub repository.

**Note on Future Contributions and CLAs:**
Should this project begin accepting code contributions from external developers in the future, signing a **Contributor License Agreement (CLA)** will be **required** before any pull requests can be merged. This policy ensures that the project maintainer receives the necessary rights to distribute all contributions under both the AGPLv3 and the commercial license options offered. Details on the CLA process will be provided if and when the project formally opens up to external code contributions.