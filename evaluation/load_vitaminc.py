import json
import logging
from typing import List, Dict, Any

# Set up logging
logger = logging.getLogger("verifier")

def load_vitaminc_dataset(data_path: str, dataset_name_tag: str = "VitaminC") -> List[Dict[str, Any]]:
    """
    Load and process the VitaminC dataset.
    
    Args:
        data_path (str): Path to the VitaminC JSONL file.
        dataset_name_tag (str): Tag to identify this dataset in logs and results.
        
    Returns:
        List[Dict[str, Any]]: Processed dataset in the format expected by the verifier.
    """
    logger.info(f"Loading {dataset_name_tag} dataset from {data_path}")
    processed_data = []
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            for line_idx, line in enumerate(f):
                try:
                    item = json.loads(line)
                    
                    # Extract the required fields
                    claim = item.get("claim")
                    evidence = item.get("evidence")
                    label = item.get("label")
                    unique_id = item.get("unique_id")
                    
                    # Check for missing essential data
                    if not claim or not evidence or not label:
                        logger.warning(f"Missing essential data in VitaminC item {line_idx}, skipping.")
                        continue
                    
                    # Map VitaminC labels to factuality scores
                    human_factuality_score = None
                    human_label_str = ""
                    
                    if label == "SUPPORTS":
                        human_factuality_score = 1.0
                        human_label_str = "yes"
                    elif label == "REFUTES":
                        human_factuality_score = 0.0
                        human_label_str = "no"
                    elif label == "NOT ENOUGH INFO":
                        human_factuality_score = 0.5
                        human_label_str = "partial"
                    else:
                        logger.warning(f"Unknown VitaminC label '{label}' for item {line_idx}, skipping.")
                        continue
                    
                    processed_data.append({
                        "id": unique_id or f"{dataset_name_tag}_{line_idx}",
                        "article": evidence,  # The evidence is used as the "article"
                        "summary": claim,     # The claim is used as the "summary" to verify
                        "human_factuality_score": human_factuality_score,
                        "human_verification_label": human_label_str,
                        "dataset_source": dataset_name_tag,
                        "original_vitaminc_label": label  # Store the original label
                    })
                    
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON for line {line_idx} in {data_path}")
                except Exception as e:
                    logger.error(f"Error processing VitaminC item {line_idx}: {e}")
    
    except FileNotFoundError:
        logger.error(f"VitaminC data file not found at {data_path}")
    except Exception as e:
        logger.error(f"Error opening or reading VitaminC data file {data_path}: {e}")
    
    logger.info(f"Loaded {len(processed_data)} samples from {dataset_name_tag} dataset.")
    return processed_data
