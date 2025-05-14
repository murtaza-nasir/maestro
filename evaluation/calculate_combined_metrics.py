import os
import json
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from collections import defaultdict, Counter
import math

# Directory containing the evaluation files
RESULTS_DIR = "verifier_results"
OUTPUT_DIR = "verifier_results"

# Datasets to include (excluding TreatFact as requested)
DATASETS = ["QAGS_CNN", "QAGS_XSUM", "VitaminC", "TreatFact"]

def map_factuality_to_score(label):
    """Maps factuality labels to numeric scores."""
    if isinstance(label, (int, float)):
        return float(label)
    if isinstance(label, str):
        label_lower = label.lower()
        if label_lower in ["yes", "true", "supported", "consistent", "accurate"]:
            return 1.0
        elif label_lower in ["no", "false", "refuted", "inconsistent", "inaccurate", "contradictory"]:
            return 0.0
        elif label_lower in ["partial", "partially supported", "partially consistent", "some_contradiction", "mostly_consistent", "needs_improvement"]:
            return 0.5
    return None

def calculate_geometric_mean(values):
    """Calculate the geometric mean of a list of values.
    
    For any negative values, we take the absolute value before calculating the geometric mean.
    For zero values, we replace with a small epsilon to avoid zero products.
    """
    # Filter out None values and NaN values
    filtered_values = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    
    if not filtered_values:
        return float('nan')
    
    # Replace zeros with a small epsilon and take absolute value of negatives
    epsilon = 1e-10
    adjusted_values = [abs(v) if v != 0 else epsilon for v in filtered_values]
    
    # Calculate geometric mean
    product = np.prod(adjusted_values)
    return product ** (1.0 / len(adjusted_values))

def compute_metrics(human_scores, model_scores):
    """Compute correlation and accuracy metrics."""
    # Filter out None values
    valid_indices = [i for i, score in enumerate(model_scores) if score is not None and human_scores[i] is not None]
    human_filtered = [human_scores[i] for i in valid_indices]
    model_filtered = [model_scores[i] for i in valid_indices]
    
    if len(valid_indices) < 2:  # Need at least 2 points for correlation
        return {
            "pearson_correlation": float('nan'),
            "pearson_p_value": float('nan'),
            "spearman_correlation": float('nan'),
            "spearman_p_value": float('nan'),
            "average_absolute_difference": float('nan'),
            "binary_accuracy": None,
            "samples_evaluated": len(valid_indices),
            "valid_samples_for_correlation": 0
        }
    
    try:
        pearson_corr, p_value_pearson = pearsonr(human_filtered, model_filtered)
        spearman_corr, p_value_spearman = spearmanr(human_filtered, model_filtered)
        avg_diff = np.mean(np.abs(np.array(human_filtered) - np.array(model_filtered)))
    except:
        pearson_corr, p_value_pearson = float('nan'), float('nan')
        spearman_corr, p_value_spearman = float('nan'), float('nan')
        avg_diff = float('nan')
    
    # Binary accuracy: >= 0.5 is "positive-like"
    human_binary = [1 if score >= 0.5 else 0 for score in human_filtered]
    model_binary = [1 if score >= 0.5 else 0 for score in model_filtered]
    
    matches = sum(h == m for h, m in zip(human_binary, model_binary))
    accuracy = matches / len(human_binary) if human_binary else 0.0
    
    return {
        "pearson_correlation": pearson_corr,
        "pearson_p_value": p_value_pearson,
        "spearman_correlation": spearman_corr,
        "spearman_p_value": p_value_spearman,
        "average_absolute_difference": avg_diff,
        "binary_accuracy": accuracy,
        "samples_evaluated": len(human_scores),
        "valid_samples_for_correlation": len(valid_indices)
    }

def compute_detailed_accuracy(human_labels, model_labels, human_scores, model_scores):
    """Compute detailed accuracy metrics including confusion matrix and per-class accuracy."""
    # Create mappings for labels to ensure consistency
    label_mapping = {
        0.0: "no",
        0.5: "partial",
        1.0: "yes"
    }
    
    # Convert scores to labels if needed
    if all(isinstance(label, (int, float)) for label in human_labels):
        human_labels = [label_mapping.get(score, "unknown") for score in human_scores]
    if all(isinstance(label, (int, float)) for label in model_labels):
        model_labels = [label_mapping.get(score, "unknown") for score in model_scores]
    
    # Calculate exact match accuracy
    exact_matches = sum(h == m for h, m in zip(human_labels, model_labels))
    exact_match_accuracy = exact_matches / len(human_labels) if human_labels else 0.0
    
    # Calculate binary accuracy
    human_binary = [1 if (label == "yes" or label == "partial") else 0 for label in human_labels]
    model_binary = [1 if (label == "yes" or label == "partial") else 0 for label in model_labels]
    binary_matches = sum(h == m for h, m in zip(human_binary, model_binary))
    binary_accuracy = binary_matches / len(human_binary) if human_binary else 0.0
    
    # Calculate per-class accuracy
    per_class_accuracy = {}
    for label in ["no", "partial", "yes"]:
        indices = [i for i, h in enumerate(human_labels) if h == label]
        if indices:
            class_matches = sum(human_labels[i] == model_labels[i] for i in indices)
            class_accuracy = class_matches / len(indices)
            per_class_accuracy[label] = {
                "accuracy": class_accuracy,
                "count": len(indices)
            }
    
    # Create confusion matrix
    confusion_matrix = {}
    for human_label in ["no", "partial", "yes"]:
        confusion_matrix[human_label] = {}
        for model_label in ["no", "partial", "yes"]:
            count = sum(1 for h, m in zip(human_labels, model_labels) 
                        if h == human_label and m == model_label)
            confusion_matrix[human_label][model_label] = count
    
    # Identify error patterns
    error_patterns = {}
    for i, (h, m) in enumerate(zip(human_labels, model_labels)):
        if h != m:
            error_key = f"{h}_predicted_as_{m}"
            error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
    
    return {
        "exact_match_accuracy": exact_match_accuracy,
        "binary_accuracy": binary_accuracy,
        "per_class_accuracy": per_class_accuracy,
        "confusion_matrix": confusion_matrix,
        "error_patterns": error_patterns,
        "total_samples": len(human_labels),
        "error_samples": len(human_labels) - exact_matches
    }

def load_model_evaluations(model_name, dataset_name):
    """Load evaluation results for a specific model and dataset."""
    model_id = model_name.replace("/", "_").replace("-", "_")
    
    # For SSUMEVAL, check for files without dataset suffix first
    if dataset_name == "SSUMEVAL":
        file_path = os.path.join(RESULTS_DIR, f"{model_id}_evaluations.json")
        if os.path.exists(file_path):
            print(f"Found SSUMEVAL file: {file_path}")
            with open(file_path, 'r') as f:
                evaluations = json.load(f)
                
            # Map SSUMEVAL keys to standard keys
            standardized_evaluations = []
            for eval_item in evaluations:
                standardized_item = {
                    "id": eval_item.get("id"),
                    "dataset_source": "SSUMEVAL",
                    "human_factuality_score": eval_item.get("human_factuality"),
                    "human_verification_label": map_score_to_label(eval_item.get("human_factuality")),
                    "model_verification_result": eval_item.get("verification_result"),
                    "model_factuality_score": eval_item.get("factuality_score"),
                    "raw_response": eval_item.get("raw_response")
                }
                standardized_evaluations.append(standardized_item)
            
            return standardized_evaluations
    
    # For FRANK dataset, treat it as SSUMEVAL
    if dataset_name == "FRANK":
        # First try with FRANK suffix
        frank_file_path = os.path.join(RESULTS_DIR, f"{model_id}_FRANK_evaluations.json")
        if os.path.exists(frank_file_path):
            print(f"Found FRANK file: {frank_file_path}")
            with open(frank_file_path, 'r') as f:
                evaluations = json.load(f)
            
            # Map FRANK evaluations to SSUMEVAL format
            standardized_evaluations = []
            for eval_item in evaluations:
                standardized_item = {
                    "id": eval_item.get("id"),
                    "dataset_source": "SSUMEVAL",  # Map FRANK to SSUMEVAL
                    "human_factuality_score": eval_item.get("human_factuality_score"),
                    "human_verification_label": eval_item.get("human_verification_label"),
                    "model_verification_result": eval_item.get("model_verification_result"),
                    "model_factuality_score": eval_item.get("model_factuality_score"),
                    "raw_response": eval_item.get("raw_response")
                }
                standardized_evaluations.append(standardized_item)
            
            return standardized_evaluations
    
    # Standard path with dataset name
    file_path = os.path.join(RESULTS_DIR, f"{model_id}_{dataset_name}_evaluations.json")
    
    if not os.path.exists(file_path):
        print(f"Warning: File not found: {file_path}")
        return []
    
    with open(file_path, 'r') as f:
        evaluations = json.load(f)
    
    return evaluations

def map_score_to_label(score):
    """Map a numeric score to a label."""
    if score is None:
        return None
    if isinstance(score, (int, float)):
        if score == 1.0:
            return "yes"
        elif score == 0.5:
            return "partial"
        elif score == 0.0:
            return "no"
    return None

def calculate_model_metrics_for_dataset(model_name, dataset_name):
    """Calculate metrics for a specific model on a specific dataset."""
    evaluations = load_model_evaluations(model_name, dataset_name)
    
    if not evaluations:
        return None
    
    human_scores = [eval.get("human_factuality_score") for eval in evaluations]
    model_scores = [eval.get("model_factuality_score") for eval in evaluations]
    human_labels = [eval.get("human_verification_label") for eval in evaluations]
    model_labels = [eval.get("model_verification_result") for eval in evaluations]
    
    # Calculate basic metrics
    metrics = compute_metrics(human_scores, model_scores)
    
    # Calculate detailed accuracy metrics
    detailed_metrics = compute_detailed_accuracy(human_labels, model_labels, human_scores, model_scores)
    
    # Combine metrics
    metrics["detailed_accuracy"] = detailed_metrics
    
    return metrics

def calculate_combined_metrics(model_name, datasets=DATASETS):
    """Calculate combined metrics for a model across multiple datasets."""
    all_human_scores = []
    all_model_scores = []
    all_human_labels = []
    all_model_labels = []
    dataset_metrics = {}
    
    for dataset in datasets:
        evaluations = load_model_evaluations(model_name, dataset)
        
        if not evaluations:
            continue
        
        # Print some debug info
        print(f"Processing {len(evaluations)} evaluations for {model_name} on {dataset}")
        if evaluations and len(evaluations) > 0:
            sample_eval = evaluations[0]
            print(f"Sample evaluation keys: {list(sample_eval.keys())}")
        
        human_scores = [eval.get("human_factuality_score") for eval in evaluations]
        model_scores = [eval.get("model_factuality_score") for eval in evaluations]
        human_labels = [eval.get("human_verification_label") for eval in evaluations]
        model_labels = [eval.get("model_verification_result") for eval in evaluations]
        
        # Filter out None values
        valid_indices = [i for i, (hs, ms, hl, ml) in enumerate(zip(human_scores, model_scores, human_labels, model_labels)) 
                         if hs is not None and ms is not None and hl is not None and ml is not None]
        
        if valid_indices:
            human_scores = [human_scores[i] for i in valid_indices]
            model_scores = [model_scores[i] for i in valid_indices]
            human_labels = [human_labels[i] for i in valid_indices]
            model_labels = [model_labels[i] for i in valid_indices]
            
            print(f"Valid evaluations for {model_name} on {dataset}: {len(valid_indices)}")
            
            all_human_scores.extend(human_scores)
            all_model_scores.extend(model_scores)
            all_human_labels.extend(human_labels)
            all_model_labels.extend(model_labels)
            
            # Calculate metrics for this dataset
            metrics = compute_metrics(human_scores, model_scores)
            detailed_metrics = compute_detailed_accuracy(human_labels, model_labels, human_scores, model_scores)
            metrics["detailed_accuracy"] = detailed_metrics
            
            dataset_metrics[dataset] = metrics
        else:
            print(f"No valid evaluations found for {model_name} on {dataset}")
            # Create empty metrics
            metrics = {
                "pearson_correlation": float('nan'),
                "pearson_p_value": float('nan'),
                "spearman_correlation": float('nan'),
                "spearman_p_value": float('nan'),
                "average_absolute_difference": float('nan'),
                "binary_accuracy": None,
                "samples_evaluated": len(evaluations),
                "valid_samples_for_correlation": 0,
                "detailed_accuracy": {
                    "exact_match_accuracy": 0.0,
                    "binary_accuracy": 0.0,
                    "per_class_accuracy": {},
                    "confusion_matrix": {},
                    "error_patterns": {},
                    "total_samples": len(evaluations),
                    "error_samples": 0
                }
            }
            dataset_metrics[dataset] = metrics
    
    # Calculate combined metrics across all datasets
    combined_metrics = compute_metrics(all_human_scores, all_model_scores)
    combined_detailed = compute_detailed_accuracy(all_human_labels, all_model_labels, all_human_scores, all_model_scores)
    combined_metrics["detailed_accuracy"] = combined_detailed
    
    # Calculate precision and recall for positive class ("yes")
    confusion = combined_detailed.get("confusion_matrix", {})
    
    # For positive class (yes)
    true_positives_pos = confusion.get("yes", {}).get("yes", 0)
    false_positives_pos = confusion.get("no", {}).get("yes", 0) + confusion.get("partial", {}).get("yes", 0)
    false_negatives_pos = confusion.get("yes", {}).get("no", 0) + confusion.get("yes", {}).get("partial", 0)
    
    # Calculate precision and recall for positive class
    precision_pos = true_positives_pos / (true_positives_pos + false_positives_pos) if (true_positives_pos + false_positives_pos) > 0 else 0
    recall_pos = true_positives_pos / (true_positives_pos + false_negatives_pos) if (true_positives_pos + false_negatives_pos) > 0 else 0
    
    # Calculate geometric mean for positive class
    positive_gmean = calculate_geometric_mean([precision_pos, recall_pos])
    
    # For negative class (no)
    true_positives_neg = confusion.get("no", {}).get("no", 0)
    false_positives_neg = confusion.get("yes", {}).get("no", 0) + confusion.get("partial", {}).get("no", 0)
    false_negatives_neg = confusion.get("no", {}).get("yes", 0) + confusion.get("no", {}).get("partial", 0)
    
    # Calculate precision and recall for negative class
    precision_neg = true_positives_neg / (true_positives_neg + false_positives_neg) if (true_positives_neg + false_positives_neg) > 0 else 0
    recall_neg = true_positives_neg / (true_positives_neg + false_negatives_neg) if (true_positives_neg + false_negatives_neg) > 0 else 0
    
    # Calculate geometric mean for negative class
    negative_gmean = calculate_geometric_mean([precision_neg, recall_neg])
    
    # Get Pearson correlation (use absolute value)
    pearson_corr = abs(combined_metrics.get("pearson_correlation", 0.0))
    
    # Calculate the three-way geometric mean
    combined_score = calculate_geometric_mean([positive_gmean, negative_gmean, pearson_corr])
    
    # Store the component values for reporting
    combined_metrics["positive_class_gmean"] = positive_gmean
    combined_metrics["negative_class_gmean"] = negative_gmean
    combined_metrics["combined_score"] = combined_score
    
    return {
        "combined": combined_metrics,
        "per_dataset": dataset_metrics
    }

def get_all_models():
    """Get a list of all models from the evaluation files."""
    models = set()
    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith("_evaluations.json"):
            parts = filename.split("_")
            
            # Handle files with dataset suffix
            if len(parts) >= 3 and parts[-2] in DATASETS:
                # Extract model name from filename
                model_id = "_".join(parts[:-2])
                # Convert back to original format
                model_name = model_id.replace("_", "/", 1)
                models.add(model_name)
            # Handle files without dataset suffix (SSUMEVAL)
            elif len(parts) == 2 and parts[-1] == "evaluations.json":
                model_id = parts[0]
                model_name = model_id.replace("_", "/", 1)
                models.add(model_name)
    
    return list(models)

def calculate_all_combined_metrics():
    """Calculate combined metrics for all models across all datasets."""
    models = get_all_models()
    all_metrics = {}
    
    for model in models:
        print(f"Calculating combined metrics for {model}...")
        metrics = calculate_combined_metrics(model)
        all_metrics[model] = metrics
    
    # Save combined metrics to file
    output_path = os.path.join(OUTPUT_DIR, "all_models_combined_metrics.json")
    with open(output_path, 'w') as f:
        json.dump(all_metrics, f, indent=2, default=lambda x: float(x) if isinstance(x, np.float32) or isinstance(x, np.float64) else x)
    
    print(f"Combined metrics saved to {output_path}")
    
    # Create a summary table
    summary = []
    for model, metrics in all_metrics.items():
        combined = metrics["combined"]
        per_class = combined["detailed_accuracy"].get("per_class_accuracy", {})
        
        row = {
            "model": model,
            "combined_score": combined.get("combined_score", float('nan')),
            "positive_class_gmean": combined.get("positive_class_gmean", float('nan')),
            "negative_class_gmean": combined.get("negative_class_gmean", float('nan')),
            "pearson_correlation": combined["pearson_correlation"],
            "binary_accuracy": combined["binary_accuracy"],
            "exact_match_accuracy": combined["detailed_accuracy"]["exact_match_accuracy"],
            "samples_evaluated": combined["samples_evaluated"]
        }
        summary.append(row)
    
    # Sort by combined score
    summary.sort(key=lambda x: x["combined_score"] if not math.isnan(x.get("combined_score", float('nan'))) else 0, reverse=True)
    
    # Save summary to CSV
    summary_df = pd.DataFrame(summary)
    summary_path = os.path.join(OUTPUT_DIR, "all_models_combined_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    
    print(f"Summary table saved to {summary_path}")
    
    return all_metrics

if __name__ == "__main__":
    calculate_all_combined_metrics()
