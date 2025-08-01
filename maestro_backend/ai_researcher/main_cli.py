import typer
from pathlib import Path
from typing import Dict, Optional, List, Set
import os
import json
import asyncio
import re
import datetime
import typer # Already imported, but good to note
from enum import Enum

from dotenv import load_dotenv

# Import core RAG components (Using absolute paths relative to project structure)
# or using `python -m ai_researcher.main_cli` which adds project root to path.
from ai_researcher.core_rag.processor import DocumentProcessor
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.vector_store_manager import VectorStoreManager as VectorStore
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.core_rag.retriever import Retriever
# --- Agentic Layer Imports ---
from ai_researcher.agentic_layer.agent_controller import AgentController
from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry, ToolDefinition
# RAG components needed for tools/agents
from ai_researcher.core_rag.query_strategist import QueryStrategist
from ai_researcher.core_rag.query_preparer import QueryPreparer
# Tool classes
from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
from ai_researcher.agentic_layer.tools.calculator_tool import CalculatorTool
from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
from ai_researcher.agentic_layer.tools.python_tool import PythonTool
from ai_researcher.agentic_layer.tools.file_reader_tool import FileReaderTool
from ai_researcher.agentic_layer.tools.web_page_fetcher_tool import WebPageFetcherTool
# --- End Agentic Layer Imports ---
from ai_researcher import config # Import config to access model names
from ai_researcher.ui.file_converters import markdown_to_pdf, markdown_to_docx

# Load environment variables (especially OPENROUTER_API_KEY)
# Look for .env in the ai_researcher directory relative to this script
dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path)


app = typer.Typer(help="AI Researcher Framework CLI - Ingest documents and query the RAG system.")

# --- Configuration Defaults (Relative to project root) ---
DEFAULT_PDF_DIR = "ai_researcher/data/raw_pdfs"
DEFAULT_MARKDOWN_DIR = "ai_researcher/data/processed/markdown"
DEFAULT_METADATA_DIR = "ai_researcher/data/processed/metadata"
DEFAULT_DB_PATH = "ai_researcher/data/processed/metadata.db"
DEFAULT_VECTOR_STORE_PATH = "ai_researcher/data/vector_store"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_MISSION_RESULTS_DIR = "ai_researcher/data/mission_results" # Default for saving mission JSON logs
DEFAULT_CLI_OUTPUT_DIR = "cli_research_output" # Default for saving markdown reports
# --- End Configuration ---


@app.command()
def ingest(
    pdf_dir: Path = typer.Option(DEFAULT_PDF_DIR, "--pdf-dir", "-p", help="Directory containing PDF files to ingest."),
    markdown_dir: Path = typer.Option(DEFAULT_MARKDOWN_DIR, "--md-dir", help="Directory to save processed Markdown files."),
    metadata_dir: Path = typer.Option(DEFAULT_METADATA_DIR, "--meta-dir", help="Directory to save extracted metadata JSON files."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", help="Path to the SQLite database for tracking processed files."),
    vector_store_path: Path = typer.Option(DEFAULT_VECTOR_STORE_PATH, "--vector-store", "-vs", help="Path to the ChromaDB vector store persistence directory."),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embed-model", help="Embedding model name (HuggingFace)."),
    batch_size_embed: int = typer.Option(16, "--batch-embed", help="Batch size for embedding generation."),
    batch_size_store: int = typer.Option(100, "--batch-store", help="Batch size for adding chunks to vector store."),
    force_reembed: bool = typer.Option(False, "--force-reembed", help="Force re-processing and re-embedding for all PDFs, even if already in the database (useful for syncing vector store)."),
):
    """
    Ingest PDF documents from a directory into the RAG system.
    Processes PDFs, extracts metadata, chunks text, generates embeddings, and stores them.
    """
    typer.echo(f"Starting ingestion process...")
    typer.echo(f"PDF Source: {pdf_dir}")
    typer.echo(f"Vector Store Path: {vector_store_path}")
    typer.echo(f"Database Path: {db_path}")

    # Ensure paths are resolved correctly relative to the current working directory
    pdf_dir = Path(pdf_dir).resolve()
    markdown_dir = Path(markdown_dir).resolve()
    metadata_dir = Path(metadata_dir).resolve()
    db_path = Path(db_path).resolve()
    vector_store_path = Path(vector_store_path).resolve()


    if not pdf_dir.is_dir():
        typer.secho(f"Error: PDF directory not found: {pdf_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        # 1. Initialize components
        typer.echo("\nInitializing components...")
        # Pass resolved absolute paths to components
        # Initialize components that DocumentProcessor needs
        embedder = TextEmbedder(model_name=embedding_model, batch_size=batch_size_embed)
        vector_store = VectorStore(persist_directory=str(vector_store_path), batch_size=batch_size_store) # Chroma needs str path

        # Initialize DocumentProcessor, passing embedder and vector_store
        processor = DocumentProcessor(
            pdf_dir=pdf_dir,
            markdown_dir=markdown_dir,
            metadata_dir=metadata_dir,
            db_path=db_path,
            embedder=embedder,         # Pass instance
            vector_store=vector_store, # Pass instance
            force_reembed=force_reembed # Pass the flag
        )
        typer.echo("Components initialized.")

        # 2. Process PDF directory (now handles embedding/storing internally)
        typer.echo("\nProcessing PDF files (including embedding and storing)...")
        total_docs_processed, total_chunks_added = processor.process_directory() # Returns counts

        if total_docs_processed == 0:
            typer.echo("No new documents were processed.")
            raise typer.Exit()

        # 3. Report results (Embedding/Storing loop removed)
        typer.secho(f"\nIngestion process finished. Processed {total_docs_processed} new documents and added {total_chunks_added} chunks to the vector store.", fg=typer.colors.GREEN)

    except Exception as e:
        typer.secho(f"\nAn error occurred during ingestion: {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        raise typer.Exit(code=1)


@app.command()
def query(
    query_text: str = typer.Argument(..., help="The query text to search for."),
    vector_store_path: Path = typer.Option(DEFAULT_VECTOR_STORE_PATH, "--vector-store", "-vs", help="Path to the ChromaDB vector store persistence directory."),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embed-model", help="Embedding model name (HuggingFace)."),
    reranker_model: str = typer.Option(DEFAULT_RERANKER_MODEL, "--rerank-model", help="Reranker model name (HuggingFace)."),
    n_results: int = typer.Option(5, "--n-results", "-k", help="Number of results to retrieve."),
    use_reranker: bool = typer.Option(True, "--rerank/--no-rerank", help="Enable/disable the reranker."),
    filter_doc_id: Optional[str] = typer.Option(None, "--filter-doc-id", help="Filter results by a specific document ID."),
    dense_weight: float = typer.Option(0.5, "--dense-weight", help="Weight for dense search results during initial retrieval."),
    sparse_weight: float = typer.Option(0.5, "--sparse-weight", help="Weight for sparse search results during initial retrieval."),
):
    """
    Query the RAG system with a text query and retrieve relevant document chunks.
    """
    typer.echo(f"Executing query: '{query_text}'")
    typer.echo(f"Vector Store Path: {vector_store_path}")
    typer.echo(f"Using Reranker: {use_reranker}")

    # Resolve path
    vector_store_path = Path(vector_store_path).resolve()

    try:
        # 1. Initialize components
        typer.echo("\nInitializing components...")
        embedder = TextEmbedder(model_name=embedding_model)
        vector_store = VectorStore(persist_directory=str(vector_store_path)) # Chroma needs str path
        reranker = TextReranker(model_name=reranker_model) if use_reranker else None
        retriever = Retriever(embedder=embedder, vector_store=vector_store, reranker=reranker)
        typer.echo("Components initialized.")

        # 2. Prepare filter if provided
        query_filter = None
        if filter_doc_id:
            query_filter = {"doc_id": filter_doc_id}
            typer.echo(f"Applying filter: {query_filter}")

        # 3. Retrieve results
        typer.echo("\nRetrieving results...")
        results = asyncio.run(retriever.retrieve(
            query_text=query_text,
            n_results=n_results,
            filter_metadata=query_filter,
            use_reranker=use_reranker,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight
        ))

        # 4. Display results
        if not results:
            typer.secho("No relevant documents found.", fg=typer.colors.YELLOW)
        else:
            typer.echo(f"\n--- Top {len(results)} Results ---")
            for i, res in enumerate(results):
                typer.echo(f"\n[{i+1}] Score: {res.get('score', 'N/A'):.4f}")
                metadata = res.get('metadata', {})
                # Try to parse JSON metadata fields back if they were stringified
                title = metadata.get('title', 'Unknown Title')
                doc_id = metadata.get('doc_id', 'Unknown ID')
                chunk_id = metadata.get('chunk_id', 'N/A')
                authors_str = metadata.get('authors', '[]')
                try:
                     authors = json.loads(authors_str) if isinstance(authors_str, str) else authors_str
                     # Filter out None values before joining
                     if isinstance(authors, list):
                         # Replace None values with empty strings and filter out empty strings
                         filtered_authors = [a for a in authors if a is not None]
                         authors_display = ", ".join(filtered_authors)
                     else:
                         authors_display = authors_str
                except json.JSONDecodeError:
                     authors_display = authors_str # Show raw string if not valid JSON list

                typer.echo(f"    Source Doc ID: {doc_id} (Chunk: {chunk_id})")
                typer.echo(f"    Title: {title}")
                typer.echo(f"    Authors: {authors_display}")
                typer.echo(f"    Text: {res.get('text', '')[:300]}...") # Display preview

    except Exception as e:
        typer.secho(f"\nAn error occurred during query: {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command()
def inspect_store(
    vector_store_path: Path = typer.Option(DEFAULT_VECTOR_STORE_PATH, "--vector-store", "-vs", help="Path to the ChromaDB vector store persistence directory."),
    list_docs: bool = typer.Option(False, "--list-docs", "-l", help="List metadata for each unique document found in the store."),
):
    """
    Inspect the vector store to get statistics like chunk count and unique document count.
    Optionally lists the metadata for each unique document.
    """
    typer.echo(f"Inspecting vector store at: {vector_store_path}")

    # Resolve path
    vector_store_path = Path(vector_store_path).resolve()

    if not vector_store_path.exists() or not vector_store_path.is_dir():
        typer.secho(f"Error: Vector store path not found or not a directory: {vector_store_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        # Initialize VectorStore to access the collection
        # We don't need embedder/reranker here, just the store access
        typer.echo("Initializing VectorStore...")
        # Use a try-except block for ChromaDB initialization issues
        try:
            vector_store = VectorStore(persist_directory=str(vector_store_path))
            collection = vector_store.dense_collection # Use the dense collection as primary
        except Exception as e_init:
            typer.secho(f"Error initializing ChromaDB client or collection: {e_init}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        typer.echo("VectorStore initialized.")

        # 1. Get total chunk count
        total_chunks = collection.count()
        typer.echo(f"\n--- Store Statistics ---")
        typer.echo(f"Total Chunks (Items): {total_chunks}")

        if total_chunks == 0:
            typer.echo("Store is empty.")
            raise typer.Exit()

        # 2. Get unique document count and metadata
        typer.echo("Retrieving metadata to analyze documents...")
        try:
            # Fetch all metadata. This could be memory intensive for huge stores.
            # Consider batching or alternative methods if performance becomes an issue.
            results = collection.get(include=['metadatas'])
            all_metadatas = results.get('metadatas', [])
        except Exception as e_get:
             typer.secho(f"Error retrieving data from ChromaDB collection: {e_get}", fg=typer.colors.RED)
             raise typer.Exit(code=1)

        if not all_metadatas:
            typer.echo("No metadata found in the store.")
            raise typer.Exit()

        unique_docs = {} # Store metadata keyed by doc_id
        for meta in all_metadatas:
            doc_id = meta.get('doc_id')
            if doc_id and doc_id not in unique_docs:
                # Store the first encountered metadata for this doc_id
                unique_docs[doc_id] = meta

        unique_doc_count = len(unique_docs)
        typer.echo(f"Unique Documents Found: {unique_doc_count}")

        # 3. List document metadata if requested
        if list_docs:
            typer.echo("\n--- Unique Document Metadata ---")
            if not unique_docs:
                typer.echo("No unique documents with metadata found.")
            else:
                sorted_doc_ids = sorted(unique_docs.keys())
                for i, doc_id in enumerate(sorted_doc_ids):
                    meta = unique_docs[doc_id]
                    typer.echo(f"\n[{i+1}] Document ID: {doc_id}")
                    # Print relevant metadata fields nicely
                    filename = meta.get('original_filename', 'N/A')
                    title = meta.get('title', 'N/A')
                    authors_str = meta.get('authors', '[]') # Stored as JSON string
                    try:
                        authors = json.loads(authors_str) if isinstance(authors_str, str) else authors_str
                        # Filter out None values before joining
                        if isinstance(authors, list):
                            # Replace None values with empty strings and filter out empty strings
                            filtered_authors = [a for a in authors if a is not None]
                            authors_display = ", ".join(filtered_authors)
                        else:
                            authors_display = authors_str
                    except json.JSONDecodeError:
                        authors_display = authors_str # Show raw string if not valid JSON list

                    typer.echo(f"    Original Filename: {filename}")
                    typer.echo(f"    Title: {title}")
                    typer.echo(f"    Authors: {authors_display}")
                    # Optionally print other metadata fields if needed
                    # for key, value in meta.items():
                    #     if key not in ['doc_id', 'original_filename', 'title', 'authors', 'chunk_id', 'text']: # Avoid redundant/large fields
                    #         typer.echo(f"    {key.replace('_', ' ').title()}: {value}")


    except Exception as e:
        typer.secho(f"\nAn error occurred during inspection: {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)


# --- Helper function to generate report filenames ---
def generate_report_filename(mission_id: str) -> str:
    """Generates a filename for a report using current date and time."""
    # Get current date and time
    now = datetime.datetime.now()
    # Format as YYYY-MM-DD_HH-MM-SS
    date_time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    # Create filename with date_time at the start for better sorting
    return f"{date_time_str}_report_{mission_id}.md"


# --- Async Helper for Running Missions ---
# We need this because Typer commands themselves are synchronous,
# but the agent controller methods are async.
async def _run_single_mission(
    agent_controller: AgentController,
    question: str,
    tool_selection: Dict[str, bool] # <-- Add tool_selection parameter
) -> Optional[str]:
    """Creates, prepares, and runs a single mission, returning the mission_id if successful."""
    mission_id: Optional[str] = None
    try:
        # 1. Create Mission Context using ContextManager
        # This method is synchronous in the current ContextManager implementation
        mission_context = agent_controller.context_manager.start_mission(user_request=question)
        mission_id = mission_context.mission_id
        typer.echo(f"Mission context created (ID: {mission_id}).")

        # 2. Generate Initial Questions using ResearchManager
        # Note: Passing log_queue/update_callback is omitted here as CLI is non-interactive
        initial_questions, model_details_gen_q = await agent_controller.research_manager._generate_first_level_questions(
            user_request=question
        )
        # Update stats for question generation (if model_details available)
        if model_details_gen_q:
            # Call stats update directly on context manager (no queue/callback needed for CLI)
            agent_controller.context_manager.update_mission_stats(mission_id, model_details_gen_q)

        if not initial_questions:
            raise ValueError("Failed to generate initial questions.")
        typer.echo(f"Generated {len(initial_questions)} initial questions.")

        # 3. Confirm Questions and Settings (using the provided tool selection)
        confirm_success = await agent_controller.confirm_questions_and_run(
            mission_id=mission_id,
            final_questions=initial_questions,
            tool_selection=tool_selection # <-- Use the passed selection
            # No log_queue/update_callback needed for CLI confirmation step
        )
        if not confirm_success:
            raise ValueError("Failed to confirm questions and settings.")
        typer.echo("Confirmed questions and settings.")

        # 4. Run the Mission using AgentController
        typer.echo(f"Running research mission {mission_id}...")
        await agent_controller.run_mission(
            mission_id=mission_id
            # No log_queue/update_callback needed for CLI run step
        )
        typer.echo(f"Mission {mission_id} execution finished.")
        return mission_id

    except Exception as e:
        typer.secho(f"Error during mission processing for question '{question}': {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc()
        # Ensure mission status is marked failed if an error occurred mid-run
        if mission_id:
            try:
                # Check current status before updating
                current_context = agent_controller.context_manager.get_mission_context(mission_id)
                if current_context and current_context.status != "failed":
                    agent_controller.context_manager.update_mission_status(mission_id, "failed", f"CLI Error: {e}")
            except Exception as status_update_e:
                typer.secho(f"Additionally failed to update mission status for {mission_id}: {status_update_e}", fg=typer.colors.YELLOW)
        return None # Indicate failure


# Define an enum for output formats
class OutputFormat(str, Enum):
    markdown = "markdown"
    pdf = "pdf"
    docx = "docx"
    all = "all"

@app.command(name="run-research")
def run_research( # Changed to synchronous 'def'
    question: Optional[str] = typer.Option(None, "--question", "-q", help="A single research question to run."),
    input_file: Optional[Path] = typer.Option(None, "--input-file", "-f", help="Path to a text file containing research questions (one per line)."),
    output_dir: Path = typer.Option(DEFAULT_CLI_OUTPUT_DIR, "--output-dir", "-o", help="Directory to save the final reports."),
    vector_store_path: Path = typer.Option(DEFAULT_VECTOR_STORE_PATH, "--vector-store", "-vs", help="Path to the ChromaDB vector store persistence directory."),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embed-model", help="Embedding model name (HuggingFace)."),
    reranker_model: str = typer.Option(DEFAULT_RERANKER_MODEL, "--rerank-model", help="Reranker model name (HuggingFace)."),
    mission_results_dir: Path = typer.Option(DEFAULT_MISSION_RESULTS_DIR, "--mission-log-dir", help="Directory to save mission context JSON logs."),
    use_local_rag: bool = typer.Option(True, "--use-local-rag/--no-use-local-rag", help="Enable/disable local document search (RAG)."),
    use_web_search: bool = typer.Option(True, "--use-web-search/--no-use-web-search", help="Enable/disable web search."),
    output_formats: List[OutputFormat] = typer.Option(
        [OutputFormat.markdown], "--format", "-fmt", 
        help="Output format(s) for the research report. Can specify multiple formats."
    ),
    # Add other relevant options if needed, e.g., specific model choices for agents
):
    """
    Run the full AI research process non-interactively for one or more questions.
    Generates a final report in the specified format(s) for each question.
    
    By default, reports are saved in Markdown format. You can specify multiple output formats
    using the --format option multiple times (e.g., --format markdown --format pdf).
    Use --format all to generate reports in all available formats.
    """
    if not question and not input_file:
        typer.secho("Error: Please provide either a single question (--question) or an input file (--input-file).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if question and input_file:
        typer.secho("Error: Please provide only one of --question or --input-file.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # --- Resolve Paths ---
    vector_store_path = Path(vector_store_path).resolve()
    output_dir = Path(output_dir).resolve()
    mission_results_dir = Path(mission_results_dir).resolve()
    if input_file:
        input_file = Path(input_file).resolve()

    # --- Read Questions ---
    questions: List[str] = []
    if question:
        questions.append(question)
    elif input_file:
        if not input_file.is_file():
            typer.secho(f"Error: Input file not found: {input_file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            with open(input_file, 'r') as f:
                questions = [line.strip() for line in f if line.strip()]
            if not questions:
                typer.secho(f"Error: Input file '{input_file}' is empty or contains no valid questions.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            typer.echo(f"Read {len(questions)} questions from {input_file}")
        except Exception as e:
            typer.secho(f"Error reading input file {input_file}: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    # --- Ensure Output Directory Exists ---
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        typer.echo(f"Output directory: {output_dir}")
    except Exception as e:
        typer.secho(f"Error creating output directory {output_dir}: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # --- Initialize Components ---
    typer.echo("\nInitializing components...")
    try:
        # RAG Components
        embedder = TextEmbedder(model_name=embedding_model)
        vector_store = VectorStore(persist_directory=str(vector_store_path))
        reranker = TextReranker(model_name=reranker_model)
        retriever = Retriever(embedder=embedder, vector_store=vector_store, reranker=reranker)

        # Agentic Layer Components
        model_dispatcher = ModelDispatcher() # Assumes API keys are in env
        query_preparer = QueryPreparer(model_dispatcher)
        query_strategist = QueryStrategist(model_dispatcher)
        tool_registry = ToolRegistry()
        context_manager = ContextManager(save_dir=str(mission_results_dir)) # Save mission logs

        # Initialize and Register Tools
        doc_search_tool = DocumentSearchTool(retriever, query_preparer, query_strategist)
        tool_registry.register_tool(ToolDefinition(name=doc_search_tool.name, description=doc_search_tool.description, parameters_schema=doc_search_tool.parameters_schema, implementation=doc_search_tool.execute))

        web_search_tool = WebSearchTool() # Assumes TAVILY_API_KEY in env
        tool_registry.register_tool(ToolDefinition(name=web_search_tool.name, description=web_search_tool.description, parameters_schema=web_search_tool.parameters_schema, implementation=web_search_tool.execute))

        web_fetcher_tool = WebPageFetcherTool()
        tool_registry.register_tool(ToolDefinition(name=web_fetcher_tool.name, description=web_fetcher_tool.description, parameters_schema=web_fetcher_tool.parameters_schema, implementation=web_fetcher_tool.execute))

        calc_tool = CalculatorTool()
        tool_registry.register_tool(ToolDefinition(name=calc_tool.name, description=calc_tool.description, parameters_schema=calc_tool.parameters_schema, implementation=calc_tool.execute))

        file_reader_tool = FileReaderTool()
        tool_registry.register_tool(ToolDefinition(name=file_reader_tool.name, description=file_reader_tool.description, parameters_schema=file_reader_tool.parameters_schema, implementation=file_reader_tool.execute))

        python_tool = PythonTool()
        tool_registry.register_tool(ToolDefinition(name=python_tool.name, description=python_tool.description, parameters_schema=python_tool.parameters_schema, implementation=python_tool.execute))

        # Agent Controller
        agent_controller = AgentController(
            model_dispatcher=model_dispatcher,
            context_manager=context_manager,
            tool_registry=tool_registry,
            retriever=retriever,
            reranker=reranker
            # query_preparer and query_strategist are initialized internally or passed to tools
        )
        typer.echo("Components initialized successfully.")

    except Exception as e:
        typer.secho(f"\nError initializing components: {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)

    # --- Run Research for Each Question ---
    typer.echo("\nStarting research missions...")
    total_questions = len(questions)
    success_count = 0
    failure_count = 0

    for i, current_question in enumerate(questions):
        typer.echo(f"\n--- Processing Question {i+1}/{total_questions} ---")
        typer.echo(f"Question: {current_question}")
        mission_id: Optional[str] = None
        try:
            # Prepare tool selection dictionary from CLI args
            current_tool_selection = {
                'local_rag': use_local_rag,
                'web_search': use_web_search
            }
            typer.echo(f"Tool Selection: Local RAG={use_local_rag}, Web Search={use_web_search}")

            # 1. Start and Run Mission using asyncio.run()
            # Pass the tool selection to the helper function
            mission_id = asyncio.run(_run_single_mission(
                agent_controller,
                current_question,
                current_tool_selection # Pass the selection dict
            ))

            if not mission_id:
                # Error messages are handled within _run_single_mission or the exception block
                failure_count += 1
                continue # Skip to the next question

            # 2. Get Final Report (after mission has run)
            typer.echo("Retrieving final report...")
            final_report = agent_controller.get_final_report(mission_id) # This is synchronous

            if final_report:
                # --- Retrieve and Format Stats ---
                stats_header = ""
                mission_stats = agent_controller.context_manager.get_mission_stats(mission_id)
                if mission_stats:
                    total_cost = mission_stats.get('total_cost', 0.0)
                    total_prompt = mission_stats.get('total_prompt_tokens', 0.0)
                    total_completion = mission_stats.get('total_completion_tokens', 0.0)
                    total_web_searches = mission_stats.get('total_web_search_calls', 0)
                    # --- Get OpenRouter Model Names Directly from Config ---
                    light_model = config.OPENROUTER_FAST_MODEL
                    heavy_model = config.OPENROUTER_MID_MODEL
                    beast_model = config.OPENROUTER_INTELLIGENT_MODEL
                    # --- Format Header ---
                    stats_header = (
                        f"<!--\n"
                        f"Mission ID: {mission_id}\n"
                        f"OpenRouter Models Configured:\n" # Clarified header text
                        f"  Light: {light_model}\n"
                        f"  Heavy: {heavy_model}\n"
                        f"  Beast: {beast_model}\n"
                        f"Stats:\n"
                        f"  Total Cost: ${total_cost:.6f}\n"
                        f"  Total Prompt Tokens: {total_prompt:.0f}\n"
                        f"  Total Completion Tokens: {total_completion:.0f}\n"
                        f"  Total Web Searches: {total_web_searches}\n"
                        f"-->\n\n"
                    )
                    typer.echo(f"OpenRouter Models: Light={light_model}, Heavy={heavy_model}, Beast={beast_model}")
                    typer.echo(f"Stats: Cost=${total_cost:.6f}, Prompt Tokens={total_prompt:.0f}, Completion Tokens={total_completion:.0f}, Web Searches={total_web_searches}")
                else:
                    typer.echo("Stats not found for this mission.")
                # --- End Stats ---

                # 4. Save Report in specified formats
                base_filename = generate_report_filename(mission_id)
                base_name = base_filename.rsplit('.', 1)[0]  # Remove extension
                
                # Determine which formats to save
                formats_to_save: Set[str] = set()
                for fmt in output_formats:
                    if fmt == OutputFormat.all:
                        formats_to_save.update([OutputFormat.markdown, OutputFormat.pdf, OutputFormat.docx])
                    else:
                        formats_to_save.add(fmt)
                
                save_success = False
                
                # Save in each requested format
                for fmt in formats_to_save:
                    try:
                        if fmt == OutputFormat.markdown:
                            # Save as Markdown
                            md_path = output_dir / f"{base_name}.md"
                            with open(md_path, 'w') as f:
                                f.write(stats_header + final_report)  # Prepend the stats header
                            typer.secho(f"Successfully saved Markdown report to: {md_path}", fg=typer.colors.GREEN)
                            save_success = True
                        
                        elif fmt == OutputFormat.pdf:
                            # Save as PDF
                            pdf_path = output_dir / f"{base_name}.pdf"
                            pdf_bytes = markdown_to_pdf(final_report)
                            with open(pdf_path, 'wb') as f:
                                f.write(pdf_bytes)
                            typer.secho(f"Successfully saved PDF report to: {pdf_path}", fg=typer.colors.GREEN)
                            save_success = True
                        
                        elif fmt == OutputFormat.docx:
                            # Save as DOCX
                            docx_path = output_dir / f"{base_name}.docx"
                            docx_bytes = markdown_to_docx(final_report)
                            with open(docx_path, 'wb') as f:
                                f.write(docx_bytes)
                            typer.secho(f"Successfully saved DOCX report to: {docx_path}", fg=typer.colors.GREEN)
                            save_success = True
                    
                    except Exception as e:
                        typer.secho(f"Error saving report in {fmt} format: {e}", fg=typer.colors.RED)
                
                if save_success:
                    success_count += 1
                else:
                    # Mission technically succeeded, but all save attempts failed
                    failure_count += 1
            else:
                # Check mission status if report is None
                mission_status = "unknown"
                mission_context = context_manager.get_mission_context(mission_id)
                if mission_context:
                    mission_status = mission_context.status
                typer.secho(f"Failed to retrieve final report for mission {mission_id}. Status: {mission_status}", fg=typer.colors.RED)
                failure_count += 1

        except Exception as e:
            typer.secho(f"An error occurred processing question '{current_question}': {e}", fg=typer.colors.RED)
            import traceback
            traceback.print_exc()
            failure_count += 1
            # Ensure mission status is marked failed if an error occurred mid-run
            if mission_id:
                try:
                    if agent_controller.context_manager.get_mission_context(mission_id).status != "failed":
                        agent_controller.context_manager.update_mission_status(mission_id, "failed", f"CLI Error: {e}")
                except Exception as status_update_e:
                    typer.secho(f"Additionally failed to update mission status for {mission_id}: {status_update_e}", fg=typer.colors.YELLOW)

    # --- Final Summary ---
    typer.echo("\n--- Research Complete ---")
    typer.echo(f"Total Questions: {total_questions}")
    typer.secho(f"Successful Reports: {success_count}", fg=typer.colors.GREEN)
    typer.secho(f"Failed Missions: {failure_count}", fg=typer.colors.RED if failure_count > 0 else typer.colors.WHITE)

    if failure_count > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    # Standard Typer entry point
    app()
