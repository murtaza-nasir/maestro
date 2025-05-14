import sys
import os
from pathlib import Path
import json

# Add project root to sys.path to allow importing ai_researcher components
# Assumes this script is run from the project root (/home/murtaza/work/papers/researcher2)
project_root = Path.cwd()
ai_researcher_path = project_root / "ai_researcher"
if str(project_root) not in sys.path:
     sys.path.insert(0, str(project_root))
if str(ai_researcher_path) not in sys.path:
     sys.path.insert(0, str(ai_researcher_path))


try:
    import chromadb
    # Import VectorStore or necessary components from your project structure
    # Adjust the import path based on your actual structure if needed
    # Assuming vector_store is accessible via ai_researcher.core_rag
    from ai_researcher.core_rag.vector_store import VectorStore
except ImportError as e:
    print(f"Error importing necessary modules: {e}")
    print(f"sys.path: {sys.path}")
    print("Ensure you are running this script from the project root '/home/murtaza/work/papers/researcher2' and the environment is active.")
    sys.exit(1)

# Configuration (match vector_store.py defaults or your config)
PERSIST_DIR = project_root / "data/vector_store"
# Use the dense collection name as it likely holds the primary metadata reference
COLLECTION_NAME = "research_papers_dense"
NUM_SAMPLES = 20 # How many records to fetch

def inspect_metadata():
    print(f"--- Vector Store Metadata Inspection ---")
    print(f"Project Root (assumed): {project_root}")
    print(f"Attempting to connect to ChromaDB at: {PERSIST_DIR}")
    if not PERSIST_DIR.exists():
        print(f"Error: Persistence directory not found: {PERSIST_DIR}")
        return

    try:
        client = chromadb.PersistentClient(path=str(PERSIST_DIR))
        print(f"Client connected.")

        # Directly try to get the collection for ChromaDB v0.6.0+
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
            print(f"Accessed collection '{COLLECTION_NAME}'. Total items: {collection.count()}")
        except Exception as e:
            print(f"Error accessing primary collection '{COLLECTION_NAME}': {e}")
            # Try the sparse collection as a fallback if the dense one fails
            alt_collection_name = "research_papers_sparse"
            print(f"Attempting fallback collection '{alt_collection_name}'...")
            try:
                 collection = client.get_collection(name=alt_collection_name)
                 print(f"Accessed collection '{alt_collection_name}'. Total items: {collection.count()}")
            except Exception as e_alt:
                 print(f"Error accessing fallback collection '{alt_collection_name}': {e_alt}")
                 print("Could not access either primary or fallback collection. Exiting.")
                 return


        if collection.count() == 0:
            print("Collection is empty. No metadata to inspect.")
            return

        # Get a sample of records including metadata
        print(f"\nFetching first {NUM_SAMPLES} records with metadata from '{collection.name}'...")
        results = collection.get(
            limit=NUM_SAMPLES,
            include=["metadatas"] # Only fetch metadata
        )

        if not results or not results.get("metadatas"):
            print("Could not retrieve metadata from the collection.")
            return

        print("\n--- Sample Metadata ('original_filename') ---")
        count = 0
        for metadata in results["metadatas"]:
            if metadata:
                # Metadata might contain JSON strings, try parsing them if needed
                # For original_filename, it should ideally be a direct string
                filename = metadata.get("original_filename", "MISSING_KEY")
                print(f"Record {count + 1}: original_filename = '{filename}'")
            else:
                print(f"Record {count + 1}: Metadata is None or empty")
            count += 1
            if count >= NUM_SAMPLES:
                 break
        print("---------------------------------------------\n")

    except Exception as e:
        print(f"An error occurred during ChromaDB interaction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_metadata()
