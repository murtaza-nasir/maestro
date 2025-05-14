import json
import os
import time
import asyncio
import random
import logging
import sys
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI
from scipy.stats import pearsonr, spearmanr
from dotenv import load_dotenv
from collections import Counter # For majority vote

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluation.load_vitaminc import load_vitaminc_dataset

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("verifier_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("verifier")

# Set up OpenRouter client with OpenAI compatibility in async mode
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    timeout=60.0  # Increase timeout to 60 seconds
)

MODELS = [
    "qwen/qwen3-32b",
    "qwen/qwen3-30b-a3b",
    "qwen/qwen3-8b",
    "openai/gpt-4o-mini",
    "meta-llama/llama-4-maverick",
    "deepseek/deepseek-chat-v3-0324",
    "openai/gpt-4.1-nano",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemini-2.5-flash-preview",
    "anthropic/claude-3.7-sonnet",
    "amazon/nova-lite-v1",
    "google/gemma-3-27b-it",
    "microsoft/phi-4",
    "qwen/qwen-2.5-7b-instruct",
    "qwen/qwen2.5-coder-7b-instruct"
]

# Parameters
MAX_SAMPLES = 300
MAX_CONCURRENT_REQUESTS = 10
MAX_CONCURRENT_MODELS = 5
REQUEST_DELAY = 1.0
MAX_RETRIES = 5
OUTPUT_DIR = "evaluation/verifier_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEBUG_DIR = os.path.join(OUTPUT_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

def sanitize_json_response(content):
    import re
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    if "```json" in content or "```" in content:
        code_block_pattern = r"```(?:json)?\n(.*?)\n```"
        matches = re.findall(code_block_pattern, content, re.DOTALL)
        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
    cleaned_content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    cleaned_content = re.sub(r"[^{}\[\]:,\"'\d.a-zA-Z_\s-]", "", cleaned_content)
    cleaned_content = cleaned_content.strip()
    json_pattern = r"({.*})"
    json_matches = re.findall(json_pattern, cleaned_content, re.DOTALL)
    if json_matches:
        for json_str in json_matches:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    cleaned_content = content.replace("'", '"')
    cleaned_content = re.sub(r"(\w+):", r'"\1":', cleaned_content)
    try:
        return json.loads(cleaned_content)
    except json.JSONDecodeError:
        pass
    return None

def map_factuality_to_score(label: Any) -> float | None:
    """Maps various factuality labels to a numeric score."""
    if isinstance(label, (int, float)): # Already a score
        return float(label)
    if isinstance(label, str):
        label_lower = label.lower()
        if label_lower in ["yes", "true", "supported", "consistent", "accurate"]:
            return 1.0
        elif label_lower in ["no", "false", "refuted", "inconsistent", "inaccurate", "contradictory"]:
            return 0.0
        elif label_lower in ["partial", "partially supported", "partially consistent", "some_contradiction", "mostly_consistent", "needs_improvement"]:
            return 0.5
        elif label_lower in ["notenoughinfo", "nei", "cannot_determine", "ambiguous"]:
            return None # Or a specific score if you prefer, e.g., -1, but None is better for filtering
    return None

def load_sentence_veracity_dataset(data_path: str, dataset_name_tag: str = "SentenceVeracity") -> List[Dict[str, Any]]:
    """
    Load and process a dataset where each line is a JSON object containing
    an article and summary sentences, each with multiple worker annotations.
    Each sentence will be treated as an individual item to verify.
    """
    # Make sure you have a logger instance. If 'logger' is not global, get one:
    current_logger = logging.getLogger("verifier." + __name__) # Or just "verifier" if that's your main logger name

    current_logger.info(f"Loading {dataset_name_tag} dataset from {data_path}")
    processed_data = []

    try:
        with open(data_path, 'r', encoding='utf-8') as f: # Added encoding
            for line_idx, line in enumerate(f):
                try:
                    item = json.loads(line)
                    article_text = item.get("article")

                    if not article_text or not str(article_text).strip():
                        current_logger.warning(f"Missing or empty 'article' in line {line_idx} of {data_path}, skipping.")
                        continue

                    summary_sentences_data = item.get("summary_sentences")
                    if not summary_sentences_data or not isinstance(summary_sentences_data, list):
                        current_logger.warning(f"Missing or invalid 'summary_sentences' in line {line_idx} of {data_path}, skipping.")
                        continue

                    for sent_idx, sent_data in enumerate(summary_sentences_data):
                        sentence_text = sent_data.get("sentence")
                        responses = sent_data.get("responses")

                        if not sentence_text or not str(sentence_text).strip() or \
                           not responses or not isinstance(responses, list) or not responses:
                            current_logger.warning(f"Missing/empty 'sentence' or invalid/empty 'responses' in summary_sentences entry {sent_idx}, line {line_idx}, skipping.")
                            continue
                            
                        vote_counts = Counter()
                        for resp in responses:
                            worker_response = resp.get("response", "").lower()
                            if worker_response in ["yes", "no"]:
                                vote_counts[worker_response] += 1
                        
                        human_label_aggregated = "cannot_determine"
                        if not vote_counts:
                            current_logger.info(f"No valid 'yes'/'no' votes for sentence in line {line_idx}, sent {sent_idx}. Labelled as 'cannot_determine'.")
                        else:
                            # Determine majority
                            most_common_votes = vote_counts.most_common() # Gets all, sorted by count
                            if len(most_common_votes) == 1: # Only one type of vote (all yes or all no)
                                human_label_aggregated = most_common_votes[0][0]
                            elif most_common_votes[0][1] == most_common_votes[1][1]: # Tie for the top spot
                                human_label_aggregated = "partial_due_to_tie"
                            else: # Clear majority
                                human_label_aggregated = most_common_votes[0][0]

                        human_factuality_score = map_factuality_to_score(human_label_aggregated)
                        
                        if human_factuality_score is None:
                            current_logger.warning(f"Could not map aggregated label '{human_label_aggregated}' to score for sentence in line {line_idx}, sent {sent_idx}. Skipping.")
                            continue

                        processed_data.append({
                            "id": f"{dataset_name_tag}_{line_idx}_{sent_idx}",
                            "article": str(article_text),
                            "summary": str(sentence_text),
                            "human_factuality_score": human_factuality_score,
                            "human_verification_label": human_label_aggregated,
                            "dataset_source": dataset_name_tag,
                            "original_responses": responses 
                        })

                except json.JSONDecodeError:
                    current_logger.error(f"Failed to parse JSON for line {line_idx} in {data_path}")
                except Exception as e:
                    current_logger.error(f"Error processing item within line {line_idx}, sentence {sent_idx if 'sent_idx' in locals() else 'N/A'} in {data_path}: {e}", exc_info=True)
                    
    except FileNotFoundError:
        current_logger.error(f"Data file not found at {data_path}")
    except Exception as e:
        current_logger.error(f"Error opening or reading data file {data_path}: {e}", exc_info=True)
            
    current_logger.info(f"Loaded {len(processed_data)} individual sentence verification samples from {dataset_name_tag} dataset ({data_path}).")
    return processed_data

def load_treatfact_dataset(data_path: str, dataset_name_tag: str = "TreatFact") -> List[Dict[str, Any]]:
    """
    Load and process the TreatFact dataset from a CSV file.
    """
    logger.info(f"Loading {dataset_name_tag} dataset from {data_path}")
    processed_data = []
    
    try:
        # Specify dtype for potentially problematic columns if necessary, though often not needed.
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        logger.error(f"TreatFact data file not found at {data_path}. Please check the path.")
        return []
    except Exception as e:
        logger.error(f"Error reading TreatFact CSV file {data_path}: {e}")
        return []

    # --- Verified Column Names ---
    article_col = 'Abstract'
    summary_col = 'Summary'  # CORRECTED based on your provided CSV
    human_label_col = 'What is the overall factuality score'
    # --- End Column Name Verification ---

    required_cols = [article_col, summary_col, human_label_col]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing required columns in TreatFact CSV ({data_path}): {', '.join(missing_cols)}. Available columns: {', '.join(df.columns)}")
        return []

    for idx, row in df.iterrows():
        article_text = row.get(article_col)
        summary_text = row.get(summary_col)
        human_raw_label = row.get(human_label_col) # This is the 0, 1, 2, or 3 score

        # Check for NaN or empty essential data
        if pd.isna(article_text) or not str(article_text).strip() or \
           pd.isna(summary_text) or not str(summary_text).strip() or \
           pd.isna(human_raw_label):
            logger.warning(f"Missing or empty essential data in TreatFact row {idx} "
                           f"(Article empty: {pd.isna(article_text) or not str(article_text).strip()}, "
                           f"Summary empty: {pd.isna(summary_text) or not str(summary_text).strip()}, "
                           f"Label empty: {pd.isna(human_raw_label)}), skipping.")
            continue
        
        human_factuality_score = None
        human_label_str_for_script = "" # The "yes", "no", "partial" label

        # Mapping TreatFact's 0-3 scale (where higher is better factuality)
        # to the script's internal 0.0, 0.5, 1.0 scale.
        try:
            # Ensure human_raw_label is treated as a number for comparison
            label_val = int(float(human_raw_label)) # Handles cases like "2.0" from CSV
            logger.info(f"Processing TreatFact row {idx} with ID {row.get('ID', 'unknown')}, raw score: {human_raw_label}, converted to: {label_val}")
        except ValueError:
            logger.warning(f"Could not convert TreatFact label '{human_raw_label}' to number for row {idx}, skipping.")
            continue

        # TreatFact uses a 0-3 scale where:
        # 3 = Fully Factual / No issues noted
        # 2 = Partially Factual / Minor issues noted
        # 1 = Largely Non-Factual / Significant issues
        # 0 = Completely Non-Factual
        if label_val == 3:
            human_factuality_score = 1.0
            human_label_str_for_script = "yes" 
        elif label_val == 2:
            human_factuality_score = 0.5
            human_label_str_for_script = "partial"
        elif label_val == 1:
            human_factuality_score = 0.0 
            human_label_str_for_script = "no" 
        elif label_val == 0:
            human_factuality_score = 0.0
            human_label_str_for_script = "no"
        else:
            logger.warning(f"Unknown TreatFact integer label value '{label_val}' (from raw: '{human_raw_label}') for row {idx}, skipping.")
            continue
            
        # This check is mostly redundant if the above if/elif/else is exhaustive for valid integer labels
        if human_factuality_score is None: 
            logger.warning(f"Internal error: Could not map TreatFact label '{human_raw_label}' to score for row {idx} despite logic, skipping.")
            continue

        processed_data.append({
            "id": f"{dataset_name_tag}_{row.get('ID', idx)}", # Use 'ID' column if available, else use row index
            "article": str(article_text),
            "summary": str(summary_text),
            "human_factuality_score": human_factuality_score,
            "human_verification_label": human_label_str_for_script, 
            "dataset_source": dataset_name_tag,
            "original_treatfact_label": human_raw_label # Store the original 0-3 score
        })
            
    logger.info(f"Loaded {len(processed_data)} samples from {dataset_name_tag} dataset ({data_path}).")
    return processed_data

def load_qags_dataset(qags_data_path: str, source_type: str = "cnn") -> List[Dict[str, Any]]:
    """
    Load and process a QAGS dataset file.
    Assumes QAGS data is in a JSONL format where each line is a JSON object.
    Expected QAGS fields (may vary based on specific QAGS version/source):
    - 'article_text' or 'document'
    - 'summary_text' or 'summary'
    - 'qags_consistency_label' (e.g., 'Consistent', 'Inconsistent', or a score from Q&A)
      Alternatively, might need to parse 'qa_pairs' if consistency is per Q&A.
      This example assumes a pre-aggregated 'overall_consistency_label' or similar.

    Args:
        qags_data_path (str): Path to the QAGS JSONL file.
        source_type (str): Identifier for the QAGS data source (e.g., "cnn", "xsum").
    """
    logger.info(f"Loading QAGS dataset from {qags_data_path} for source {source_type}")
    processed_data = []
    with open(qags_data_path, 'r') as f:
        for i, line in enumerate(f):
            try:
                item = json.loads(line)
                
                article = item.get('article_text') or item.get('document') or item.get('source_article')
                summary = item.get('summary_text') or item.get('summary') or item.get('generated_summary')
                
                # This is the tricky part for QAGS as it depends on how consistency is stored.
                # Option 1: An overall label exists
                human_label = item.get('qags_consistency_label') or item.get('overall_consistency') or item.get('factuality_label')

                # Option 2: Derive from QA pairs (more complex, example shown below)
                if human_label is None and 'qa_pairs' in item:
                    consistent_count = 0
                    total_pairs = len(item['qa_pairs'])
                    if total_pairs == 0:
                        human_label = "cannot_determine" # Or skip
                    else:
                        for qa_pair in item['qa_pairs']:
                            # Assuming qa_pair has a 'consistency' field (e.g., 'consistent', 'inconsistent')
                            if qa_pair.get('consistency', '').lower() == 'consistent':
                                consistent_count += 1
                        
                        if consistent_count == total_pairs:
                            human_label = "consistent"
                        elif consistent_count == 0:
                            human_label = "inconsistent"
                        else:
                            human_label = "partial" # Or "mostly_consistent" etc.

                if not article or not summary or human_label is None:
                    logger.warning(f"Missing required fields (article, summary, or label) in QAGS item {i}, skipping. Item: {item}")
                    continue

                human_factuality_score = map_factuality_to_score(human_label)

                if human_factuality_score is None:
                    logger.warning(f"Could not map QAGS label '{human_label}' to score for item {i}, skipping.")
                    continue
                
                # Create a unique ID, e.g., from a hash or an existing ID field
                item_id = item.get('id') or item.get('summary_id') or f"qags_{source_type}_{i}"

                processed_data.append({
                    "id": item_id,
                    "article": article,
                    "summary": summary,
                    "human_factuality_score": human_factuality_score,
                    "human_verification_label": human_label,
                    "dataset_source": f"QAGS_{source_type.upper()}"
                })
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON for line {i} in {qags_data_path}")
            except Exception as e:
                logger.error(f"Error processing QAGS item {i}: {e}")
                
    logger.info(f"Loaded {len(processed_data)} samples from QAGS dataset ({qags_data_path}).")
    return processed_data


def get_dataset_specific_prompt(article: str, summary: str, dataset_source: str = None) -> str:
    """
    Generate a dataset-specific prompt based on the dataset source.
    Different datasets may benefit from different prompting strategies.
    """
    if dataset_source and "vitaminc" in dataset_source.lower():
        # VitaminC-specific prompt for claim verification
        return f"""You are a fact-checking expert specializing in claim verification. Your task is to carefully analyze the provided evidence and assess whether it supports, refutes, or provides insufficient information for the given claim.

Following is the evidence to analyze:
<<evidence>>
{article}
<</evidence>>

Please verify if the evidence supports this claim:
<<claim>>
{summary}
<</claim>>

Based on the evidence above, analyze whether the claim is supported by the evidence. Consider:
1. Does the evidence directly support the claim?
2. Does the evidence directly contradict the claim?
3. Does the evidence provide insufficient information to determine if the claim is true or false?

Provide your answer strictly in the following JSON format:
{{
  "verification_result": "yes | no | partial"
}}

Where:
- "yes" means the claim is fully supported by the evidence (equivalent to SUPPORTS)
- "no" means the claim is contradicted by the evidence (equivalent to REFUTES)
- "partial" means the evidence provides insufficient information to verify the claim (equivalent to NOT ENOUGH INFO)
"""
    elif dataset_source and "treatfact" in dataset_source.lower():
        # TreatFact-specific prompt for scientific abstracts
        return f"""You are an evidence-based medicine expert evaluating the factual consistency of a summary of a clinical study abstract. Factual consistency means ALL information in the summary must be accurately supported by the abstract.

You must carefully analyze these specific elements:

1. POPULATION: Are the study participants (including eligibility criteria, demographics, and clinical characteristics) described accurately?

2. INTERVENTION: Is the treatment or procedure being evaluated described correctly?

3. COMPARISON: Are any comparison treatments correctly represented?

4. OUTCOMES: Are the measured outcomes and results precisely reported without exaggeration or minimization?

5. STRENGTH OF CLAIM: Does the summary maintain the same level of certainty as the abstract (e.g., definitive vs. tentative language)?

6. DIRECTION OF CONCLUSION: Does the summary correctly state whether the intervention had a positive, negative, or neutral effect?

A summary is INCONSISTENT if ANY of these occur:
- Important population details are omitted or misrepresented
- Intervention details are changed or imprecise
- Comparison treatments are inaccurate
- Outcome measures are exaggerated or minimized
- The strength of claims is inflated beyond what's in the abstract
- The direction of effect is incorrectly stated

Abstract:
<<abstract>>
{article}
<</abstract>>

Summary:
<<summary>>
{summary}
<</summary>>

First, evaluate each component separately:
1. Population consistency (yes/no/partial):
2. Intervention consistency (yes/no/partial):
3. Comparison consistency (yes/no/partial):
4. Outcomes consistency (yes/no/partial):
5. Strength of claim consistency (yes/no/partial):
6. Direction consistency (yes/no/partial):

Based on these assessments, provide your final verdict in JSON format:
{{
  "verification_result": "yes | partial | no"
}}

Where:
- "yes" means completely consistent (ALL elements are accurate)
- "partial" means some inconsistencies exist but core findings are preserved
- "no" means significant factual errors exist that could mislead a reader
"""
    elif dataset_source and ("qags" in dataset_source.lower() or "cnn" in dataset_source.lower() or "xsum" in dataset_source.lower()):
        # News article specific prompt
        return f"""You are a fact-checking expert specializing in news articles. Your task is to carefully analyze the provided article and assess whether it supports the specified summary.

Following is the news article to analyze:
<<article>>
{article}
<</article>>

Please verify if the article supports this summary:
<<summary>>
{summary}
<</summary>>

Based on the article above, analyze whether the summary is factually supported by the article's content. Consider:
1. Are all claims in the summary supported by the article?
2. Does the summary misrepresent any facts, quotes, or events?
3. Does the summary include information not present in the article?

Provide your answer strictly in the following JSON format:
{{
  "verification_result": "yes | no | partial"
}}

Where:
- "yes" means the summary is fully supported by the article
- "no" means the summary contains significant factual errors or misrepresentations
- "partial" means the summary is partially supported but contains some inaccuracies
"""
    else:
        # Default prompt for general content
        return f"""You are a fact-checking expert. Your task is to carefully analyze the provided article and assess whether it supports the specified claim.

Following is the article to analyze:
<<article>>
{article}
<</article>>

Please verify if the article supports this claim:
<<claim>>
{summary}
<</claim>>

Based on the article above, analyze whether the claim is supported by the article's content. Provide your answer strictly in the following JSON format:
{{
  "verification_result": "yes | no | partial"
}}

Where:
- "yes" means the claim is fully supported by the article
- "no" means the claim contains significant factual errors or misrepresentations
- "partial" means the claim is partially supported but contains some inaccuracies
"""

async def evaluate_factual_consistency(article: str, summary: str, model: str,
                                       semaphore: asyncio.Semaphore = None,
                                       max_retries: int = 5,
                                       dataset_source: str = None) -> Dict[str, Any]:
    
    # Get the appropriate prompt based on the dataset source
    prompt = get_dataset_specific_prompt(article, summary, dataset_source)

    retry_count = 0
    base_delay = 1
    
    while retry_count <= max_retries:
        try:
            api_call_params = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 512, # Increased slightly just in case, though 64 should be enough for yes/no/partial
                "response_format": {
                    "type": "json_schema", # Note: Changed from "json_object" to "json_schema" as per your original script
                    "json_schema": {
                        "name": "verification",
                        "strict": True, # For stricter adherence to the schema
                        "schema": {
                            "type": "object",
                            "properties": {
                                "verification_result": {
                                    "type": "string",
                                    "enum": ["yes", "no", "partial"],
                                    "description": "Whether the claim is supported by the article"
                                }
                            },
                            "required": ["verification_result"],
                            "additionalProperties": False
                        }
                    }
                }
            }

            if semaphore:
                async with semaphore:
                    response = await client.chat.completions.create(**api_call_params)
            else:
                response = await client.chat.completions.create(**api_call_params)
            
            if retry_count > 0:
                logger.info(f"Success after {retry_count} retries for model {model}")
            
            content = response.choices[0].message.content.strip() if response.choices else None
            
            if not content:
                raise ValueError(f"Empty response content from model {model}")
                
            result = sanitize_json_response(content)
            if result is None:
                logger.error(f"JSON parsing error for model {model}. Raw content: {repr(content)}")
                raise json.JSONDecodeError(f"Could not parse JSON from response: {repr(content)}", "", 0)
            
            verification_result_str = result.get("verification_result", "").lower()
            if not verification_result_str:
                raise ValueError(f"Missing verification_result in response: {result}")
            
            factuality_score = map_factuality_to_score(verification_result_str)
            if factuality_score is None: # Should not happen if enum is respected by model
                raise ValueError(f"Invalid verification_result '{verification_result_str}' from model {model}")

            return {
                "verification_result": verification_result_str,
                "factuality_score": factuality_score,
                "raw_response": content
            }
            
        except Exception as e:
            retry_count += 1
            if retry_count <= max_retries:
                delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                logger.error(f"Error in API call for model {model} (item: {summary[:50]}...): {e}")
                logger.info(f"Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Failed after {max_retries} retries for model {model} (item: {summary[:50]}...): {e}")
                return {
                    "verification_result": None,
                    "factuality_score": None,
                    "raw_response": f"Error after {max_retries} retries: {str(e)}"
                }

async def evaluate_samples_for_model(model: str, dataset: List[Dict[str, Any]],
                                     max_concurrent: int = 3,
                                     request_delay: float = 0.5) -> List[Dict]:
    model_results = []
    tasks = []
    semaphore = asyncio.Semaphore(max_concurrent)
    
    model_short_name = model.split('/')[-1]
    logger.info(f"Evaluating {len(dataset)} samples with {model_short_name} in parallel...")
    
    # Create all tasks first without awaiting them
    for item in dataset:
        article = item["article"]
        summary = item["summary"]
        dataset_source = item.get("dataset_source", None)
        
        # Create a task for this sample
        task = asyncio.create_task(evaluate_factual_consistency(
            article, summary, model, semaphore, max_retries=MAX_RETRIES, dataset_source=dataset_source
        ))
        # Store task with metadata
        tasks.append({"item_data": item, "task": task})
    
    # Process tasks as they complete for maximum concurrency
    successful = 0
    failed = 0
    
    # Use as_completed to process tasks in the order they complete
    pending_tasks = [task_info["task"] for task_info in tasks]
    
    for completed_task in async_tqdm(asyncio.as_completed(pending_tasks), 
                                    total=len(pending_tasks), 
                                    desc=f"Processing {model_short_name}"):
        # Find the task_info that corresponds to the completed task
        task_info = next(info for info in tasks if info["task"] == completed_task)
        item_data = task_info["item_data"]
        
        try:
            evaluation = await completed_task
            
            if evaluation["verification_result"] is None:
                failed += 1
                logger.warning(f"Failed evaluation for item {item_data['id']}, model {model_short_name}")
            else:
                successful += 1
                
            model_results.append({
                "id": item_data["id"],
                "dataset_source": item_data.get("dataset_source", "unknown"),
                "human_factuality_score": item_data["human_factuality_score"],
                "human_verification_label": item_data.get("human_verification_label"),
                "model_verification_result": evaluation["verification_result"],
                "model_factuality_score": evaluation["factuality_score"],
                "raw_response": evaluation["raw_response"]
            })
            
        except Exception as e:
            failed += 1
            logger.error(f"Exception processing task for item {item_data['id']} for model {model_short_name}: {e}")
            model_results.append({
                "id": item_data["id"],
                "dataset_source": item_data.get("dataset_source", "unknown"),
                "human_factuality_score": item_data["human_factuality_score"],
                "human_verification_label": item_data.get("human_verification_label"),
                "model_verification_result": None,
                "model_factuality_score": None,
                "raw_response": f"Task exception: {str(e)}"
            })
    
    logger.info(f"Model {model_short_name} evaluation complete: {successful} successful, {failed} failed")
    return model_results

def save_raw_responses(model_results, model_name, dataset_name_tag=""):
    model_filename = model_name.replace("/", "_").replace("-", "_")
    dataset_tag_suffix = f"_{dataset_name_tag}" if dataset_name_tag else ""
    raw_responses_path = os.path.join(DEBUG_DIR, f"{model_filename}{dataset_tag_suffix}_raw_responses.txt")
    
    with open(raw_responses_path, 'w') as f:
        for i, result in enumerate(model_results):
            f.write(f"=== Sample ID: {result['id']} ===\n")
            
            # Get human and model scores for comparison
            human_score = result.get('human_factuality_score')
            model_score = result.get('model_factuality_score')
            human_label = result.get('human_verification_label', 'unknown')
            model_result = result.get('model_verification_result', 'unknown')
            
            # Determine if model is correct (within binary classification)
            is_correct = "unknown"
            if human_score is not None and model_score is not None:
                # Binary classification: treat scores >= 0.5 as positive, < 0.5 as negative
                human_binary = 1 if human_score >= 0.5 else 0
                model_binary = 1 if model_score >= 0.5 else 0
                is_correct = "correct" if human_binary == model_binary else "incorrect"
            
            f.write(f"Model Verification result: {model_result}\n")
            f.write(f"Human Verification label: {human_label}\n")
            f.write(f"Human factuality score: {human_score}\n")
            f.write(f"Model factuality score: {model_score}\n")
            f.write(f"Model accuracy: {is_correct}\n")
            f.write(f"Raw response:\n{result['raw_response']}\n\n")
    
    logger.info(f"Raw responses for {model_name} on {dataset_name_tag or 'dataset'} saved to {raw_responses_path}")

def compute_detailed_accuracy(results_df: pd.DataFrame, dataset_source: str = None):
    """
    Compute more detailed accuracy metrics, especially for the TreatFact and VitaminC datasets.
    This includes per-class accuracy, confusion matrix, etc.
    """
    if results_df.empty:
        return {
            "detailed_accuracy": None,
            "confusion_matrix": None,
            "per_class_accuracy": None,
            "error_analysis": None
        }
    
    # Filter out rows with missing values
    valid_df = results_df.dropna(subset=["human_factuality_score", "model_factuality_score"])
    
    if valid_df.empty:
        return {
            "detailed_accuracy": None,
            "confusion_matrix": None,
            "per_class_accuracy": None,
            "error_analysis": None
        }
    
    # For VitaminC dataset, analyze based on the original labels (SUPPORTS, REFUTES, NOT ENOUGH INFO)
    if dataset_source and "vitaminc" in dataset_source.lower():
        # Check if we have the original VitaminC labels
        if "original_vitaminc_label" in valid_df.columns:
            # Create a mapping from the original VitaminC labels to descriptive labels
            label_mapping = {
                "SUPPORTS": "supports",
                "REFUTES": "refutes",
                "NOT ENOUGH INFO": "not_enough_info"
            }
            
            # Map the human verification labels to the original VitaminC labels
            human_label_to_vitaminc = {
                "yes": "SUPPORTS",
                "no": "REFUTES",
                "partial": "NOT ENOUGH INFO"
            }
            
            # Map the model's verification results to the VitaminC labels
            model_result_to_vitaminc = {
                "yes": "SUPPORTS",
                "no": "REFUTES",
                "partial": "NOT ENOUGH INFO"
            }
            
            # Calculate exact match accuracy (model's prediction matches human's original label)
            exact_matches = 0
            for _, row in valid_df.iterrows():
                human_original = row.get("original_vitaminc_label")
                model_result = row.get("model_verification_result")
                if model_result and model_result_to_vitaminc.get(model_result) == human_original:
                    exact_matches += 1
            
            exact_match_accuracy = exact_matches / len(valid_df) if len(valid_df) > 0 else 0
            
            # Calculate per-class accuracy
            per_class_accuracy = {}
            for original_label, label_desc in label_mapping.items():
                class_df = valid_df[valid_df["original_vitaminc_label"] == original_label]
                if not class_df.empty:
                    class_matches = 0
                    for _, row in class_df.iterrows():
                        model_result = row.get("model_verification_result")
                        if model_result and model_result_to_vitaminc.get(model_result) == original_label:
                            class_matches += 1
                    
                    class_accuracy = class_matches / len(class_df)
                    per_class_accuracy[label_desc] = {
                        "accuracy": class_accuracy,
                        "count": len(class_df)
                    }
            
            # Create a confusion matrix
            confusion_matrix = {}
            for human_label, human_desc in label_mapping.items():
                confusion_matrix[human_desc] = {}
                for model_label, model_desc in label_mapping.items():
                    count = 0
                    for _, row in valid_df.iterrows():
                        if row.get("original_vitaminc_label") == human_label:
                            model_result = row.get("model_verification_result")
                            if model_result and model_result_to_vitaminc.get(model_result) == model_label:
                                count += 1
                    
                    confusion_matrix[human_desc][model_desc] = count
            
            # Calculate sensitivity and specificity for each class
            sensitivity_specificity = {}
            for label, desc in label_mapping.items():
                # For each class, calculate:
                # - True Positives (TP): Model correctly predicts this class
                # - False Negatives (FN): Model incorrectly predicts another class when it should be this class
                # - False Positives (FP): Model incorrectly predicts this class when it should be another class
                # - True Negatives (TN): Model correctly predicts another class when it should be another class
                
                TP = 0
                FN = 0
                FP = 0
                TN = 0
                
                for _, row in valid_df.iterrows():
                    human_original = row.get("original_vitaminc_label")
                    model_result = row.get("model_verification_result")
                    model_predicted = model_result_to_vitaminc.get(model_result) if model_result else None
                    
                    if human_original == label and model_predicted == label:
                        TP += 1
                    elif human_original == label and model_predicted != label:
                        FN += 1
                    elif human_original != label and model_predicted == label:
                        FP += 1
                    elif human_original != label and model_predicted != label:
                        TN += 1
                
                sensitivity = TP / (TP + FN) if (TP + FN) > 0 else 0
                specificity = TN / (TN + FP) if (TN + FP) > 0 else 0
                f1_score = 2 * TP / (2 * TP + FP + FN) if (2 * TP + FP + FN) > 0 else 0
                
                sensitivity_specificity[desc] = {
                    "sensitivity": sensitivity,
                    "specificity": specificity,
                    "f1_score": f1_score,
                    "true_positives": TP,
                    "false_negatives": FN,
                    "false_positives": FP,
                    "true_negatives": TN
                }
            
            # Identify common error patterns
            error_df = valid_df[valid_df.apply(lambda row: 
                model_result_to_vitaminc.get(row.get("model_verification_result")) != row.get("original_vitaminc_label"), 
                axis=1)]
            
            error_patterns = {}
            for _, row in error_df.iterrows():
                human_original = row.get("original_vitaminc_label")
                model_result = row.get("model_verification_result")
                model_predicted = model_result_to_vitaminc.get(model_result) if model_result else "unknown"
                
                error_key = f"{label_mapping.get(human_original, human_original)}_predicted_as_{label_mapping.get(model_predicted, model_predicted)}"
                error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
            
            return {
                "exact_match_accuracy": exact_match_accuracy,
                "per_class_accuracy": per_class_accuracy,
                "confusion_matrix": confusion_matrix,
                "sensitivity_specificity": sensitivity_specificity,
                "error_patterns": error_patterns,
                "total_samples": len(valid_df),
                "error_samples": len(error_df)
            }
    
    # For TreatFact dataset, analyze based on the original TreatFact scores (0-3)
    elif dataset_source and "treatfact" in dataset_source.lower():
        # Check if we have the original TreatFact labels
        if "original_treatfact_label" in valid_df.columns:
            # Create a mapping from the original TreatFact scores to descriptive labels
            label_mapping = {
                0: "completely_non_factual",
                1: "largely_non_factual",
                2: "partially_factual",
                3: "fully_factual"
            }
            
            # Convert original TreatFact labels to integers if they're not already
            valid_df["original_treatfact_label"] = valid_df["original_treatfact_label"].astype(float).astype(int)
            
            # Map the original TreatFact labels to descriptive labels
            valid_df["human_label_desc"] = valid_df["original_treatfact_label"].map(label_mapping)
            
            # Map the model's factuality scores to the TreatFact scale
            # 1.0 -> 3 (fully factual)
            # 0.5 -> 2 (partially factual)
            # 0.0 -> 1 (largely non-factual) or 0 (completely non-factual)
            # We'll map 0.0 to 1 for simplicity
            model_score_to_treatfact = {
                1.0: 3,  # yes -> fully factual
                0.5: 2,  # partial -> partially factual
                0.0: 1   # no -> largely non-factual
            }
            valid_df["model_treatfact_score"] = valid_df["model_factuality_score"].map(model_score_to_treatfact)
            valid_df["model_label_desc"] = valid_df["model_treatfact_score"].map(label_mapping)
            
            # Calculate exact match accuracy (model's TreatFact score matches human's TreatFact score)
            exact_matches = sum(valid_df["original_treatfact_label"] == valid_df["model_treatfact_score"])
            exact_match_accuracy = exact_matches / len(valid_df)
            
            # Calculate binary accuracy (factual vs. non-factual)
            # TreatFact scores 2-3 are considered factual, 0-1 are considered non-factual
            human_binary = [1 if score >= 2 else 0 for score in valid_df["original_treatfact_label"]]
            model_binary = [1 if score >= 2 else 0 for score in valid_df["model_treatfact_score"]]
            binary_matches = sum(h == m for h, m in zip(human_binary, model_binary))
            binary_accuracy = binary_matches / len(valid_df)
            
            # Calculate per-class accuracy
            per_class_accuracy = {}
            for label_val, label_desc in label_mapping.items():
                class_df = valid_df[valid_df["original_treatfact_label"] == label_val]
                if not class_df.empty:
                    class_matches = sum(class_df["original_treatfact_label"] == class_df["model_treatfact_score"])
                    class_accuracy = class_matches / len(class_df)
                    per_class_accuracy[label_desc] = {
                        "accuracy": class_accuracy,
                        "count": len(class_df)
                    }
            
            # Create a confusion matrix
            confusion_matrix = {}
            for human_label, human_desc in label_mapping.items():
                confusion_matrix[human_desc] = {}
                for model_label, model_desc in label_mapping.items():
                    count = len(valid_df[(valid_df["original_treatfact_label"] == human_label) & 
                                         (valid_df["model_treatfact_score"] == model_label)])
                    confusion_matrix[human_desc][model_desc] = count
            
            # Identify common error patterns
            error_df = valid_df[valid_df["original_treatfact_label"] != valid_df["model_treatfact_score"]]
            error_patterns = {}
            for human_label, model_label in zip(error_df["original_treatfact_label"], error_df["model_treatfact_score"]):
                error_key = f"{label_mapping[human_label]}_predicted_as_{label_mapping[model_label]}"
                error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
            
            return {
                "exact_match_accuracy": exact_match_accuracy,
                "binary_accuracy": binary_accuracy,
                "per_class_accuracy": per_class_accuracy,
                "confusion_matrix": confusion_matrix,
                "error_patterns": error_patterns,
                "total_samples": len(valid_df),
                "error_samples": len(error_df)
            }
    
    # For other datasets or if TreatFact doesn't have original labels
    # Calculate accuracy based on the mapped factuality scores (0.0, 0.5, 1.0)
    human_scores = valid_df["human_factuality_score"].tolist()
    model_scores = valid_df["model_factuality_score"].tolist()
    
    # Calculate exact match accuracy
    exact_matches = sum(h == m for h, m in zip(human_scores, model_scores))
    exact_match_accuracy = exact_matches / len(valid_df)
    
    # Calculate binary accuracy (factual vs. non-factual)
    human_binary = [1 if score >= 0.5 else 0 for score in human_scores]
    model_binary = [1 if score >= 0.5 else 0 for score in model_scores]
    binary_matches = sum(h == m for h, m in zip(human_binary, model_binary))
    binary_accuracy = binary_matches / len(valid_df)
    
    # Calculate per-class accuracy
    score_mapping = {
        0.0: "no",
        0.5: "partial",
        1.0: "yes"
    }
    per_class_accuracy = {}
    for score, label in score_mapping.items():
        class_df = valid_df[valid_df["human_factuality_score"] == score]
        if not class_df.empty:
            class_matches = sum(class_df["human_factuality_score"] == class_df["model_factuality_score"])
            class_accuracy = class_matches / len(class_df)
            per_class_accuracy[label] = {
                "accuracy": class_accuracy,
                "count": len(class_df)
            }
    
    # Create a confusion matrix
    confusion_matrix = {}
    for human_score, human_label in score_mapping.items():
        confusion_matrix[human_label] = {}
        for model_score, model_label in score_mapping.items():
            count = len(valid_df[(valid_df["human_factuality_score"] == human_score) & 
                                 (valid_df["model_factuality_score"] == model_score)])
            confusion_matrix[human_label][model_label] = count
    
    # Identify common error patterns
    error_df = valid_df[valid_df["human_factuality_score"] != valid_df["model_factuality_score"]]
    error_patterns = {}
    for human_score, model_score in zip(error_df["human_factuality_score"], error_df["model_factuality_score"]):
        error_key = f"{score_mapping[human_score]}_predicted_as_{score_mapping[model_score]}"
        error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
    
    return {
        "exact_match_accuracy": exact_match_accuracy,
        "binary_accuracy": binary_accuracy,
        "per_class_accuracy": per_class_accuracy,
        "confusion_matrix": confusion_matrix,
        "error_patterns": error_patterns,
        "total_samples": len(valid_df),
        "error_samples": len(error_df)
    }

def compute_metrics(results_df: pd.DataFrame, dataset_source: str = None):
    human_scores = results_df["human_factuality_score"].tolist()
    model_scores = results_df["model_factuality_score"].tolist()

    valid_indices = [i for i, score in enumerate(model_scores) if score is not None and human_scores[i] is not None]
    human_filtered = [human_scores[i] for i in valid_indices]
    model_filtered = [model_scores[i] for i in valid_indices]
    
    if len(valid_indices) < 2: # Need at least 2 points for correlation
        return {
            "pearson_correlation": None, "pearson_p_value": None,
            "spearman_correlation": None, "spearman_p_value": None,
            "average_absolute_difference": None, "binary_accuracy": None,
            "samples_evaluated": len(valid_indices), "valid_samples_for_correlation": 0
        }
    
    pearson_corr, p_value_pearson = pearsonr(human_filtered, model_filtered)
    spearman_corr, p_value_spearman = spearmanr(human_filtered, model_filtered)
    avg_diff = np.mean(np.abs(np.array(human_filtered) - np.array(model_filtered)))
    
    # Binary accuracy: human score >= 0.75 is positive, model score >= 0.75 is positive
    # (Using 0.75 to clearly separate 'yes' (1.0) from 'partial' (0.5))
    # Or more simply, treat 1.0 as positive, and <1.0 as negative if 'partial' is not a clear "positive"
    # For a 3-way (yes/no/partial), you might consider other metrics like macro F1.
    # Here, let's stick to your original binary approach: >= 0.5 is "positive-like"
    human_binary = [1 if score >= 0.5 else 0 for score in human_filtered]
    model_binary = [1 if score >= 0.5 else 0 for score in model_filtered] # Model output is already 0, 0.5, 1
    
    matches = sum(h == m for h, m in zip(human_binary, model_binary))
    accuracy = matches / len(human_binary) if human_binary else 0.0
    
    return {
        "pearson_correlation": pearson_corr, "pearson_p_value": p_value_pearson,
        "spearman_correlation": spearman_corr, "spearman_p_value": p_value_spearman,
        "average_absolute_difference": avg_diff, "binary_accuracy": accuracy,
        "samples_evaluated": len(results_df),
        "valid_samples_for_correlation": len(valid_indices)
    }

def create_comparison_visualizations(all_models_metrics: Dict[str, Dict[str, Any]], dataset_name_tag: str = ""):
    """
    Create visualizations comparing the performance of different models on a dataset.
    Now includes detailed accuracy metrics for better analysis.
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        dataset_suffix = f"_{dataset_name_tag}" if dataset_name_tag else ""
        dataset_title_suffix = f" ({dataset_name_tag})" if dataset_name_tag else ""

        models = list(all_models_metrics.keys())
        if not models:
            logger.warning("No model metrics to visualize.")
            return

        model_short_names = [model.split('/')[-1] for model in models]
        
        # Filter out metrics that might be None before plotting
        pearson_correlations = [all_models_metrics[model].get('pearson_correlation', np.nan) for model in models]
        spearman_correlations = [all_models_metrics[model].get('spearman_correlation', np.nan) for model in models]
        binary_accuracies = [all_models_metrics[model].get('binary_accuracy', np.nan) for model in models]

        x = np.arange(len(models))
        width = 0.25
        
        plt.figure(figsize=(15, 8))
        plt.bar(x - width, pearson_correlations, width, label='Pearson Correlation')
        plt.bar(x, spearman_correlations, width, label='Spearman Correlation')
        plt.bar(x + width, binary_accuracies, width, label='Binary Accuracy')
        
        plt.xlabel('Models')
        plt.ylabel('Score')
        plt.title(f'Comparison of Model Performance Metrics{dataset_title_suffix}')
        plt.xticks(x, model_short_names, rotation=45, ha='right')
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, f"model_comparison_metrics{dataset_suffix}.png"))
        plt.close()

        fig, ax = plt.subplots(figsize=(15, 8)) # Adjusted for potentially more columns
        ax.axis('tight')
        ax.axis('off')
        
        table_data = []
        for model in models:
            metrics = all_models_metrics[model]
            model_name_short = model.split('/')[-1]
            row = [
                model_name_short,
                f"{metrics.get('pearson_correlation', np.nan):.4f}",
                f"{metrics.get('spearman_correlation', np.nan):.4f}",
                f"{metrics.get('binary_accuracy', np.nan):.4f}",
                f"{metrics.get('average_absolute_difference', np.nan):.4f}",
                f"{metrics.get('samples_evaluated', 0)}",
                f"{metrics.get('valid_samples_for_correlation',0)}"
            ]
            table_data.append(row)
        
        col_labels = ['Model', 'Pearson', 'Spearman', 'Binary Acc', 'Avg Diff', 'Eval Samples', 'Corr. Samples']
        table = ax.table(cellText=table_data, colLabels=col_labels, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        plt.title(f'Detailed Metrics Comparison{dataset_title_suffix}')
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, f"model_comparison_table{dataset_suffix}.png"))
        plt.close()
        
        # Distribution of verification results (requires access to raw results, not just metrics)
        # This part needs model_results_dfs passed to it, or re-read from files
        # For now, commenting out, but can be re-added if needed by passing the right data.
        # create_verification_distribution_chart(all_models_results_dfs, models, dataset_name_tag)

        logger.info(f"Comparison visualizations for {dataset_name_tag or 'dataset'} created successfully.")
    except ImportError:
        logger.error("Required visualization libraries not installed. Skipping visualizations. Try: pip install matplotlib seaborn")
    except Exception as e:
        logger.error(f"Error creating visualizations: {e}")


async def run_evaluation_for_dataset(
    dataset_name: str,
    dataset_load_func, # Pass the function itself
    dataset_args: tuple, # Arguments for the load function
    max_samples: int | None,
    models_to_evaluate: List[str],
    max_concurrent_reqs: int,
    max_concurrent_mdls: int,
    req_delay: float
):
    logger.info(f"--- Starting evaluation for dataset: {dataset_name} ---")
    
    # Load data using the provided function and arguments
    full_dataset = dataset_load_func(*dataset_args)
    
    if not full_dataset:
        logger.error(f"No data loaded for {dataset_name}. Skipping evaluation for this dataset.")
        return {}, {}

    if max_samples:
        dataset_to_process = random.sample(full_dataset, min(len(full_dataset), max_samples)) if len(full_dataset) > max_samples else full_dataset
        logger.info(f"Using {len(dataset_to_process)} samples for {dataset_name} (Max samples: {max_samples})")
    else:
        dataset_to_process = full_dataset
        logger.info(f"Using all {len(dataset_to_process)} samples for {dataset_name}")

    # Initialize results storage for each model
    all_model_results_dfs = {} # Store DataFrames of results per model
    all_results_by_model = {model: [] for model in models_to_evaluate}
    comparison_metrics_for_dataset = {}
    
    # Create a semaphore to limit concurrent requests across all models
    semaphore = asyncio.Semaphore(max_concurrent_reqs)
    
    # Process samples in batches to avoid overwhelming memory
    batch_size = 10  # Adjust based on your needs
    total_batches = (len(dataset_to_process) + batch_size - 1) // batch_size
    
    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(dataset_to_process))
        current_batch = dataset_to_process[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_idx + 1}/{total_batches} for {dataset_name} ({batch_end - batch_start} samples)")
        
        # Create tasks for all model-sample combinations in this batch
        tasks = []
        
        for item in current_batch:
            article = item["article"]
            summary = item["summary"]
            dataset_source = item.get("dataset_source", None)
            
            for model_id_str in models_to_evaluate:
                # Create a task for each model-sample combination
                task = asyncio.create_task(evaluate_factual_consistency(
                    article, summary, model_id_str, 
                    semaphore=semaphore, 
                    max_retries=MAX_RETRIES, 
                    dataset_source=dataset_source
                ))
                
                # Store task with metadata
                tasks.append({
                    "task": task,
                    "model": model_id_str,
                    "item": item
                })
        
        # Process all tasks concurrently with a progress bar
        completed_tasks = []
        for task_data in tqdm(tasks, desc=f"Batch {batch_idx+1}/{total_batches}"):
            try:
                # Wait for this task to complete
                evaluation = await task_data["task"]
                model_id_str = task_data["model"]
                item = task_data["item"]
                
                # Create a result entry
                result_entry = {
                    "id": item["id"],
                    "dataset_source": item.get("dataset_source", "unknown"),
                    "human_factuality_score": item["human_factuality_score"],
                    "human_verification_label": item.get("human_verification_label"),
                    "model_verification_result": evaluation["verification_result"],
                    "model_factuality_score": evaluation["factuality_score"],
                    "raw_response": evaluation["raw_response"]
                }
                
                # Add to the model's results list
                all_results_by_model[model_id_str].append(result_entry)
                completed_tasks.append(task_data)
                
            except Exception as e:
                model_id_str = task_data["model"]
                item = task_data["item"]
                logger.error(f"Error processing sample {item.get('id', 'unknown')} with model {model_id_str}: {e}")
                
                # Add error entry
                all_results_by_model[model_id_str].append({
                    "id": item["id"],
                    "dataset_source": item.get("dataset_source", "unknown"),
                    "human_factuality_score": item["human_factuality_score"],
                    "human_verification_label": item.get("human_verification_label"),
                    "model_verification_result": None,
                    "model_factuality_score": None,
                    "raw_response": f"Error: {str(e)}"
                })
        
        # Log batch completion
        logger.info(f"Completed batch {batch_idx + 1}/{total_batches} for {dataset_name} - {len(completed_tasks)} tasks processed")
    
    # Process results for each model
    for model_id_str in models_to_evaluate:
        model_results_list = all_results_by_model[model_id_str]
            
        model_filename_base = model_id_str.replace("/", "_").replace("-", "_")
        dataset_tag = f"_{dataset_name}"

        # Save detailed results (list of dicts) to JSON
        with open(os.path.join(OUTPUT_DIR, f"{model_filename_base}{dataset_tag}_evaluations.json"), 'w') as f:
            json.dump(model_results_list, f, indent=2)
        
        save_raw_responses(model_results_list, model_id_str, dataset_name)
        
        df = pd.DataFrame(model_results_list)
        all_model_results_dfs[model_id_str] = df # Store for potential later use (e.g. combined viz)

        # Save CSV (can exclude raw_response if too verbose for CSV)
        df_for_csv = df.drop(columns=['raw_response'], errors='ignore')
        df_for_csv.to_csv(os.path.join(OUTPUT_DIR, f"{model_filename_base}{dataset_tag}_evaluations.csv"), index=False)
        
        # Compute standard metrics
        metrics = compute_metrics(df, dataset_name) # Pass DataFrame and dataset name to compute_metrics
        
        # Compute detailed accuracy metrics
        detailed_metrics = compute_detailed_accuracy(df, dataset_name)
        
        # Combine metrics
        combined_metrics = {**metrics, "detailed_accuracy": detailed_metrics}
        
        # Save combined metrics
        with open(os.path.join(OUTPUT_DIR, f"{model_filename_base}{dataset_tag}_metrics.json"), 'w') as f:
            json.dump(combined_metrics, f, indent=2)
        
        comparison_metrics_for_dataset[model_id_str] = combined_metrics
        
        model_short_name = model_id_str.split('/')[-1]
        print(f"\nEvaluation Results for {model_short_name} on {dataset_name}:")
        print(f"Samples evaluated: {metrics['samples_evaluated']}")
        print(f"Valid samples for correlation: {metrics['valid_samples_for_correlation']}")
        if metrics['pearson_correlation'] is not None:
            print(f"Pearson correlation: {metrics['pearson_correlation']:.4f} (p-value: {metrics['pearson_p_value']:.4f})")
            print(f"Spearman correlation: {metrics['spearman_correlation']:.4f} (p-value: {metrics['spearman_p_value']:.4f})")
            print(f"Binary accuracy: {metrics['binary_accuracy']:.4f}")
            print(f"Average absolute difference: {metrics['average_absolute_difference']:.4f}")
        else:
            print("Correlation metrics could not be computed (likely due to insufficient valid samples).")

        if not df.empty:
            result_counts = df['model_verification_result'].value_counts()
            print(f"\nDistribution of {model_short_name}'s verification results on {dataset_name}:")
            for res_val, count in result_counts.items():
                print(f"  {res_val}: {count} ({count/len(df)*100:.1f}%)")
        else:
            print(f"No results to display distribution for {model_short_name} on {dataset_name}.")
            
        # Print detailed accuracy metrics if available
        if detailed_metrics:
            print(f"\nDetailed Accuracy Metrics for {model_short_name} on {dataset_name}:")
            if "exact_match_accuracy" in detailed_metrics:
                print(f"Exact match accuracy: {detailed_metrics['exact_match_accuracy']:.4f}")
            
            if "per_class_accuracy" in detailed_metrics and detailed_metrics["per_class_accuracy"]:
                print("\nPer-class accuracy:")
                for class_label, class_metrics in detailed_metrics["per_class_accuracy"].items():
                    print(f"  {class_label}: {class_metrics['accuracy']:.4f} (count: {class_metrics['count']})")
            
            if "error_patterns" in detailed_metrics and detailed_metrics["error_patterns"]:
                print("\nCommon error patterns:")
                for error_pattern, count in sorted(detailed_metrics["error_patterns"].items(), key=lambda x: x[1], reverse=True):
                    print(f"  {error_pattern}: {count}")
            
            if dataset_name == "TreatFact" and "confusion_matrix" in detailed_metrics and detailed_metrics["confusion_matrix"]:
                print("\nConfusion Matrix:")
                # Get all unique labels from the confusion matrix
                labels = list(detailed_metrics["confusion_matrix"].keys())
                
                # Print header row
                header = "Human \\ Model |"
                for label in labels:
                    header += f" {label} |"
                print(header)
                
                # Print separator row
                separator = "-------------|"
                for _ in labels:
                    separator += "------------|"
                print(separator)
                
                # Print data rows
                for human_label in labels:
                    row = f"{human_label} |"
                    for model_label in labels:
                        count = detailed_metrics["confusion_matrix"][human_label].get(model_label, 0)
                        row += f" {count} |"
                    print(row)
                
    logger.info(f"--- Finished evaluation for dataset: {dataset_name} ---")
    return all_model_results_dfs, comparison_metrics_for_dataset


async def test_single_api_call(model="anthropic/claude-3.7-sonnet"):
    # (Your existing test_single_api_call function - unchanged)
    logger.info(f"Testing single API call to model: {model}")
    test_prompt = """You are a fact-checking expert. Please verify if the following statement is true:
"The sky is blue during a clear day."
Provide your answer strictly in the following JSON format:
{
  "verification_result": "yes | no | partial"
}"""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": test_prompt}],
            temperature=0.0,
            max_tokens=64,
            response_format={
                "type": "json_schema",
                 "json_schema": {
                    "name": "verification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"verification_result": {"type": "string", "enum": ["yes", "no", "partial"]}},
                        "required": ["verification_result"],
                        "additionalProperties": False
                    }
                }
            }
        )
        logger.info(f"Full response object: {response}")
        content = response.choices[0].message.content.strip() if response.choices else None
        logger.info(f"Response content: {repr(content)}")
        if content:
            result = sanitize_json_response(content)
            if result:
                logger.info(f"Parsed JSON: {result}")
                return True
            else:
                logger.error(f"Could not parse JSON from response: {repr(content)}")
                return False
        else:
            logger.error("Empty response content")
            return False
    except Exception as e:
        logger.error(f"API call error: {e}")
        return False


async def main_async():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        model_to_test = sys.argv[2] if len(sys.argv) > 2 else "anthropic/claude-3.7-sonnet"
        print(f"Testing single API call to {model_to_test}...")
        await test_single_api_call(model_to_test)
        return

    # --- Define datasets to evaluate ---
    # Each entry is a dictionary specifying how to load and tag the dataset.
    datasets_to_run = [
        {
            "name": "QAGS_CNN", 
            "loader_func": load_sentence_veracity_dataset,
            "loader_args": ("/home/murtaza/work/papers/researcher2/datasets/qags/data/mturk_cnndm.jsonl", "cnn"), 
            "enabled": False 
        },
        {
            "name": "QAGS_XSUM", 
            "loader_func": load_sentence_veracity_dataset,
            "loader_args": ("/home/murtaza/work/papers/researcher2/datasets/qags/data/mturk_xsum.jsonl", "xsum"), 
            "enabled": False
        },
        {
            "name": "TreatFact",  
            "loader_func": load_treatfact_dataset, 
            "loader_args": ("/home/murtaza/work/papers/researcher2/datasets/treatfact/TreatFact.csv", "TreatFact"), 
            "enabled": False 
        },
        {
            "name": "VitaminC",
            "loader_func": load_vitaminc_dataset,
            "loader_args": ("/home/murtaza/work/papers/researcher2/datasets/vitaminC/data.json", "VitaminC"),
            "enabled": False
        }
    ]

    overall_comparison_metrics = {} # To store metrics from all datasets for a final summary if needed
    enabled_datasets = [d for d in datasets_to_run if d.get("enabled", False)]
    
    if not enabled_datasets:
        logger.warning("No datasets are enabled for evaluation. Please enable at least one dataset.")
        return
        
    # Process each enabled dataset
    dataset_tasks = []
    
    for dataset_config in enabled_datasets:
        dataset_name = dataset_config["name"]
        loader_func = dataset_config["loader_func"]
        loader_args = dataset_config["loader_args"]
        
        # Check if data files exist before trying to load
        paths_to_check = [arg for arg in loader_args if isinstance(arg, str) and ("/" in arg or "\\" in arg)]
        paths_exist = all(os.path.exists(path) for path in paths_to_check)
        if not paths_exist:
            logger.error(f"One or more data paths for dataset '{dataset_name}' not found: {paths_to_check}. Skipping this dataset.")
            missing_paths_msg = "\n".join([f"  - {path}" for path in paths_to_check if not os.path.exists(path)])
            print(f"Error: Data files for '{dataset_name}' not found. Please check these paths:\n{missing_paths_msg}")
            continue

        # Create a task for this dataset
        task = asyncio.create_task(run_evaluation_for_dataset(
            dataset_name=dataset_name,
            dataset_load_func=loader_func,
            dataset_args=loader_args,
            max_samples=MAX_SAMPLES,
            models_to_evaluate=MODELS,
            max_concurrent_reqs=MAX_CONCURRENT_REQUESTS,
            max_concurrent_mdls=MAX_CONCURRENT_MODELS,
            req_delay=REQUEST_DELAY
        ))
        
        dataset_tasks.append((dataset_name, task))
    
    # Wait for all dataset tasks to complete
    for dataset_name, task in dataset_tasks:
        try:
            _, model_metrics_for_this_dataset = await task
            overall_comparison_metrics[dataset_name] = model_metrics_for_this_dataset

            if model_metrics_for_this_dataset:
                # Save comparison data for this dataset
                serializable_metrics = {
                    model: {k: (float(v) if isinstance(v, (np.float64, np.float32)) else v) for k, v in metrics.items()}
                    for model, metrics in model_metrics_for_this_dataset.items()
                }
                with open(os.path.join(OUTPUT_DIR, f"all_models_comparison_{dataset_name}.json"), 'w') as f:
                    json.dump(serializable_metrics, f, indent=2)
                
                # Create comparative visualizations for this dataset
                create_comparison_visualizations(model_metrics_for_this_dataset, dataset_name)

                # Generate model rankings for this dataset
                print(f"\n--- Model Rankings for {dataset_name} ---")
                if any(m.get('pearson_correlation') is not None for m in model_metrics_for_this_dataset.values()):
                    pearson_ranking = sorted(
                        [(model, metrics.get('pearson_correlation')) for model, metrics in model_metrics_for_this_dataset.items() if metrics.get('pearson_correlation') is not None],
                        key=lambda x: x[1], reverse=True
                    )
                    print("\nRanking by Pearson correlation:")
                    for i, (model, score) in enumerate(pearson_ranking):
                        print(f"{i+1}. {model.split('/')[-1]}: {score:.4f}")
                
                if any(m.get('binary_accuracy') is not None for m in model_metrics_for_this_dataset.values()):
                    accuracy_ranking = sorted(
                        [(model, metrics.get('binary_accuracy')) for model, metrics in model_metrics_for_this_dataset.items() if metrics.get('binary_accuracy') is not None],
                        key=lambda x: x[1], reverse=True
                    )
                    print("\nRanking by Binary accuracy:")
                    for i, (model, score) in enumerate(accuracy_ranking):
                        print(f"{i+1}. {model.split('/')[-1]}: {score:.4f}")
            else:
                logger.info(f"No metrics generated for dataset {dataset_name}, skipping visualizations and rankings.")
        except Exception as e:
            logger.error(f"Error processing dataset {dataset_name}: {e}")
    
    logger.info("All dataset evaluations complete.")


def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
