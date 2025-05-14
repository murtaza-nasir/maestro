import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from math import sqrt
from matplotlib.colors import LinearSegmentedColormap

# Set style for plots
plt.style.use('ggplot')
sns.set_palette("viridis")
sns.set_context("talk")

# Custom colormap for heatmaps
cmap = LinearSegmentedColormap.from_list("custom_cmap", ["#f8766d", "#00ba38", "#619cff"])

# Directory for results
RESULTS_DIR = "verifier_results"
OUTPUT_DIR = "visualizations"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load the combined metrics
def load_combined_metrics():
    with open(os.path.join(RESULTS_DIR, "all_models_combined_metrics.json"), 'r') as f:
        return json.load(f)

def calculate_sensitivity_specificity(confusion_matrix, class_label="yes"):
    """
    Calculate sensitivity and specificity for a specific class.
    
    For binary classification:
    - When class_label="yes": 
      - TP = confusion_matrix["yes"]["yes"]
      - FN = confusion_matrix["yes"]["no"] + confusion_matrix["yes"]["partial"]
      - FP = confusion_matrix["no"]["yes"] + confusion_matrix["partial"]["yes"]
      - TN = confusion_matrix["no"]["no"] + confusion_matrix["no"]["partial"] + 
             confusion_matrix["partial"]["no"] + confusion_matrix["partial"]["partial"]
    
    - When class_label="no":
      - TP = confusion_matrix["no"]["no"]
      - FN = confusion_matrix["no"]["yes"] + confusion_matrix["no"]["partial"]
      - FP = confusion_matrix["yes"]["no"] + confusion_matrix["partial"]["no"]
      - TN = confusion_matrix["yes"]["yes"] + confusion_matrix["yes"]["partial"] + 
             confusion_matrix["partial"]["yes"] + confusion_matrix["partial"]["partial"]
    """
    # Initialize counters
    TP = 0
    FN = 0
    FP = 0
    TN = 0
    
    # All possible labels
    all_labels = ["yes", "no", "partial"]
    
    # Calculate TP, FN, FP, TN
    for true_label in all_labels:
        for pred_label in all_labels:
            count = confusion_matrix.get(true_label, {}).get(pred_label, 0)
            
            if true_label == class_label and pred_label == class_label:
                TP += count
            elif true_label == class_label and pred_label != class_label:
                FN += count
            elif true_label != class_label and pred_label == class_label:
                FP += count
            elif true_label != class_label and pred_label != class_label:
                TN += count
    
    # Calculate metrics
    sensitivity = TP / (TP + FN) if (TP + FN) > 0 else 0
    specificity = TN / (TN + FP) if (TN + FP) > 0 else 0
    balanced_accuracy = (sensitivity + specificity) / 2
    geometric_mean = sqrt(sensitivity * specificity)
    f1_score = 2 * TP / (2 * TP + FP + FN) if (2 * TP + FP + FN) > 0 else 0
    
    return {
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "geometric_mean": geometric_mean,
        "f1_score": f1_score,
        "true_positives": TP,
        "false_negatives": FN,
        "false_positives": FP,
        "true_negatives": TN
    }

def extract_model_metrics(metrics_data):
    """Extract and calculate balanced metrics for all models and datasets."""
    model_metrics = {}
    
    for model_name, model_data in metrics_data.items():
        model_metrics[model_name] = {
            "combined": {},
            "per_dataset": {}
        }
        
        # Process combined metrics
        combined_data = model_data["combined"]
        if "detailed_accuracy" in combined_data and "confusion_matrix" in combined_data["detailed_accuracy"]:
            confusion_matrix = combined_data["detailed_accuracy"]["confusion_matrix"]
            
            # Calculate metrics for "yes" class (factual)
            yes_metrics = calculate_sensitivity_specificity(confusion_matrix, "yes")
            model_metrics[model_name]["combined"]["yes_class"] = yes_metrics
            
            # Calculate metrics for "no" class (non-factual)
            no_metrics = calculate_sensitivity_specificity(confusion_matrix, "no")
            model_metrics[model_name]["combined"]["no_class"] = no_metrics
            
            # Add standard metrics
            model_metrics[model_name]["combined"]["pearson"] = combined_data.get("pearson_correlation")
            model_metrics[model_name]["combined"]["spearman"] = combined_data.get("spearman_correlation")
            model_metrics[model_name]["combined"]["binary_accuracy"] = combined_data.get("binary_accuracy")
            model_metrics[model_name]["combined"]["exact_match"] = combined_data["detailed_accuracy"].get("exact_match_accuracy")
            model_metrics[model_name]["combined"]["samples"] = combined_data.get("samples_evaluated")
        
        # Process per-dataset metrics
        for dataset, dataset_data in model_data["per_dataset"].items():
            model_metrics[model_name]["per_dataset"][dataset] = {}
            
            if "detailed_accuracy" in dataset_data and "confusion_matrix" in dataset_data["detailed_accuracy"]:
                confusion_matrix = dataset_data["detailed_accuracy"]["confusion_matrix"]
                
                # Calculate metrics for "yes" class
                yes_metrics = calculate_sensitivity_specificity(confusion_matrix, "yes")
                model_metrics[model_name]["per_dataset"][dataset]["yes_class"] = yes_metrics
                
                # Calculate metrics for "no" class
                no_metrics = calculate_sensitivity_specificity(confusion_matrix, "no")
                model_metrics[model_name]["per_dataset"][dataset]["no_class"] = no_metrics
                
                # Add standard metrics
                model_metrics[model_name]["per_dataset"][dataset]["pearson"] = dataset_data.get("pearson_correlation")
                model_metrics[model_name]["per_dataset"][dataset]["spearman"] = dataset_data.get("spearman_correlation")
                model_metrics[model_name]["per_dataset"][dataset]["binary_accuracy"] = dataset_data.get("binary_accuracy")
                model_metrics[model_name]["per_dataset"][dataset]["exact_match"] = dataset_data["detailed_accuracy"].get("exact_match_accuracy")
                model_metrics[model_name]["per_dataset"][dataset]["samples"] = dataset_data.get("samples_evaluated")
    
    return model_metrics

def create_model_comparison_dataframe(model_metrics):
    """Create a DataFrame for model comparison across datasets."""
    rows = []
    
    for model_name, model_data in model_metrics.items():
        # Get combined metrics
        combined = model_data["combined"]
        
        # Create a row for combined metrics
        row = {
            "model": model_name.split("/")[-1],  # Use short model name
            "dataset": "Combined",
            "geometric_mean_yes": combined.get("yes_class", {}).get("geometric_mean"),
            "geometric_mean_no": combined.get("no_class", {}).get("geometric_mean"),
            "balanced_accuracy_yes": combined.get("yes_class", {}).get("balanced_accuracy"),
            "balanced_accuracy_no": combined.get("no_class", {}).get("balanced_accuracy"),
            "f1_score_yes": combined.get("yes_class", {}).get("f1_score"),
            "f1_score_no": combined.get("no_class", {}).get("f1_score"),
            "sensitivity_yes": combined.get("yes_class", {}).get("sensitivity"),
            "specificity_yes": combined.get("yes_class", {}).get("specificity"),
            "sensitivity_no": combined.get("no_class", {}).get("sensitivity"),
            "specificity_no": combined.get("no_class", {}).get("specificity"),
            "pearson": combined.get("pearson"),
            "spearman": combined.get("spearman"),
            "binary_accuracy": combined.get("binary_accuracy"),
            "exact_match": combined.get("exact_match"),
            "samples": combined.get("samples")
        }
        rows.append(row)
        
        # Add rows for each dataset
        for dataset, dataset_data in model_data["per_dataset"].items():
            row = {
                "model": model_name.split("/")[-1],
                "dataset": dataset,
                "geometric_mean_yes": dataset_data.get("yes_class", {}).get("geometric_mean"),
                "geometric_mean_no": dataset_data.get("no_class", {}).get("geometric_mean"),
                "balanced_accuracy_yes": dataset_data.get("yes_class", {}).get("balanced_accuracy"),
                "balanced_accuracy_no": dataset_data.get("no_class", {}).get("balanced_accuracy"),
                "f1_score_yes": dataset_data.get("yes_class", {}).get("f1_score"),
                "f1_score_no": dataset_data.get("no_class", {}).get("f1_score"),
                "sensitivity_yes": dataset_data.get("yes_class", {}).get("sensitivity"),
                "specificity_yes": dataset_data.get("yes_class", {}).get("specificity"),
                "sensitivity_no": dataset_data.get("no_class", {}).get("sensitivity"),
                "specificity_no": dataset_data.get("no_class", {}).get("specificity"),
                "pearson": dataset_data.get("pearson"),
                "spearman": dataset_data.get("spearman"),
                "binary_accuracy": dataset_data.get("binary_accuracy"),
                "exact_match": dataset_data.get("exact_match"),
                "samples": dataset_data.get("samples")
            }
            rows.append(row)
    
    return pd.DataFrame(rows)

def plot_model_comparison(df, metric="geometric_mean_yes", title=None):
    """Create a bar plot comparing models across datasets for a specific metric."""
    # Filter to only include the Combined dataset
    combined_df = df[df["dataset"] == "Combined"].copy()
    
    # Sort by the metric
    combined_df = combined_df.sort_values(by=metric, ascending=False)
    
    # Create the plot
    plt.figure(figsize=(12, 8))
    
    # Create bar plot
    ax = sns.barplot(x="model", y=metric, data=combined_df)
    
    # Add value labels on top of bars
    for i, v in enumerate(combined_df[metric]):
        if not pd.isna(v):
            ax.text(i, v + 0.01, f"{v:.3f}", ha="center")
    
    # Set title and labels
    if title:
        plt.title(title)
    else:
        plt.title(f"Model Comparison by {metric.replace('_', ' ').title()}")
    
    plt.xlabel("Model")
    plt.ylabel(metric.replace("_", " ").title())
    
    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha="right")
    
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(os.path.join(OUTPUT_DIR, f"model_comparison_{metric}.png"))
    plt.close()

def plot_dataset_comparison(df, metric="geometric_mean_yes"):
    """Create a grouped bar plot comparing models across datasets for a specific metric."""
    # Filter out the Combined dataset
    dataset_df = df[df["dataset"] != "Combined"].copy()
    
    # Pivot the data to have models as rows and datasets as columns
    pivot_df = dataset_df.pivot(index="model", columns="dataset", values=metric)
    
    # Sort by the average metric value across datasets
    pivot_df["avg"] = pivot_df.mean(axis=1)
    pivot_df = pivot_df.sort_values(by="avg", ascending=False)
    pivot_df = pivot_df.drop(columns=["avg"])
    
    # Calculate min and max values for the color scale
    # Add a small buffer (10% of the range) to each end to make the scale slightly wider
    data_min = pivot_df.min().min()
    data_max = pivot_df.max().max()
    value_range = data_max - data_min
    vmin = max(0, data_min - value_range * 0.1)  # Don't go below 0
    vmax = min(1, data_max + value_range * 0.1)  # Don't go above 1
    
    # Create the plot
    plt.figure(figsize=(14, 10))
    
    # Create heatmap with adjusted color scale
    sns.heatmap(pivot_df, annot=True, cmap=cmap, fmt=".3f", linewidths=0.5, vmin=vmin, vmax=vmax)
    
    # Set title and labels
    plt.title(f"Model Performance Across Datasets by {metric.replace('_', ' ').title()}")
    plt.xlabel("Dataset")
    plt.ylabel("Model")
    
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(os.path.join(OUTPUT_DIR, f"dataset_comparison_{metric}.png"))
    plt.close()

def plot_metric_correlation(df, x_metric="geometric_mean_yes", y_metric="binary_accuracy"):
    """Create a scatter plot showing correlation between two metrics."""
    # Filter to only include the Combined dataset
    combined_df = df[df["dataset"] == "Combined"].copy()
    
    # Create the plot
    plt.figure(figsize=(10, 8))
    
    # Create scatter plot
    ax = sns.scatterplot(x=x_metric, y=y_metric, data=combined_df, s=100)
    
    # Add model labels to points
    for i, row in combined_df.iterrows():
        ax.text(row[x_metric] + 0.01, row[y_metric], row["model"], fontsize=9)
    
    # Add trend line
    sns.regplot(x=x_metric, y=y_metric, data=combined_df, scatter=False, ax=ax)
    
    # Calculate correlation
    correlation = combined_df[[x_metric, y_metric]].corr().iloc[0, 1]
    
    # Set title and labels
    plt.title(f"Correlation between {x_metric.replace('_', ' ').title()} and {y_metric.replace('_', ' ').title()}\nCorrelation: {correlation:.3f}")
    plt.xlabel(x_metric.replace("_", " ").title())
    plt.ylabel(y_metric.replace("_", " ").title())
    
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(os.path.join(OUTPUT_DIR, f"metric_correlation_{x_metric}_{y_metric}.png"))
    plt.close()

def plot_radar_chart(df, metrics=None):
    """Create a radar chart comparing top models across multiple metrics."""
    if metrics is None:
        metrics = ["geometric_mean_yes", "geometric_mean_no", "f1_score_yes", "f1_score_no", "pearson"]
    
    # Filter to only include the Combined dataset
    combined_df = df[df["dataset"] == "Combined"].copy()
    
    # Sort by geometric_mean_yes and take top 5 models
    top_models = combined_df.sort_values(by="geometric_mean_yes", ascending=False).head(5)["model"].tolist()
    
    # Filter to only include top models
    top_df = combined_df[combined_df["model"].isin(top_models)]
    
    # Create the plot
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, polar=True)
    
    # Number of metrics
    N = len(metrics)
    
    # Angle for each metric
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]  # Close the loop
    
    # Plot each model
    for i, model in enumerate(top_models):
        model_data = top_df[top_df["model"] == model]
        
        # Get values for each metric
        values = [model_data[metric].values[0] for metric in metrics]
        values += values[:1]  # Close the loop
        
        # Plot the model
        ax.plot(angles, values, linewidth=2, linestyle='solid', label=model)
        ax.fill(angles, values, alpha=0.1)
    
    # Set labels for each metric
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([metric.replace("_", " ").title() for metric in metrics])
    
    # Set y-axis limits
    ax.set_ylim(0, 1)
    
    # Add legend
    plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
    
    plt.title("Top 5 Models Across Multiple Metrics")
    
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(os.path.join(OUTPUT_DIR, "radar_chart_top_models.png"))
    plt.close()

def create_summary_table(df):
    """Create a summary table of model performance."""
    # Filter to only include the Combined dataset
    combined_df = df[df["dataset"] == "Combined"].copy()
    
    # Select relevant columns
    summary_cols = [
        "model", "geometric_mean_yes", "geometric_mean_no", 
        "f1_score_yes", "f1_score_no", "pearson", "spearman", 
        "binary_accuracy", "exact_match", "samples"
    ]
    
    summary_df = combined_df[summary_cols].copy()
    
    # Sort by geometric_mean_yes
    summary_df = summary_df.sort_values(by="geometric_mean_yes", ascending=False)
    
    # Save to CSV
    summary_df.to_csv(os.path.join(OUTPUT_DIR, "model_performance_summary.csv"), index=False)
    
    return summary_df

def create_combined_ranking(df):
    """Create a combined ranking based on multiple metrics."""
    # Filter to only include the Combined dataset
    combined_df = df[df["dataset"] == "Combined"].copy()
    
    # Define the metrics to rank by
    key_metrics = ["geometric_mean_yes", "geometric_mean_no", "pearson"]
    
    # Create a new DataFrame to store rankings and scores
    ranking_df = combined_df[["model"]].copy()
    
    # For each metric, rank the models and assign scores
    for metric in key_metrics:
        # Sort by the metric in descending order and get ranks
        ranking_df[f"{metric}_rank"] = combined_df[metric].rank(ascending=False, method='min')
        
        # Store the actual metric value for reference
        ranking_df[metric] = combined_df[metric]
    
    # Calculate combined score (lower is better since it's based on ranks)
    ranking_df["combined_score"] = ranking_df[[f"{metric}_rank" for metric in key_metrics]].sum(axis=1)
    
    # Sort by combined score (ascending, since lower rank is better)
    ranking_df = ranking_df.sort_values(by="combined_score")
    
    # Add an overall rank column
    ranking_df["overall_rank"] = range(1, len(ranking_df) + 1)
    
    # Save to CSV
    ranking_df.to_csv(os.path.join(OUTPUT_DIR, "model_combined_ranking.csv"), index=False)
    
    return ranking_df

def plot_combined_ranking(ranking_df):
    """Create a visualization of the combined ranking."""
    # Sort by overall rank
    plot_df = ranking_df.sort_values(by="overall_rank").copy()
    
    # Select top models to display (to avoid overcrowding)
    top_n = min(15, len(plot_df))
    plot_df = plot_df.head(top_n)
    
    # Create a figure with subplots
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Create a bar plot of the combined score
    bars = ax.barh(plot_df["model"], plot_df["combined_score"], color='skyblue')
    
    # Add rank labels to the bars
    for i, (_, row) in enumerate(plot_df.iterrows()):
        ax.text(row["combined_score"] + 0.1, i, f"Rank: {int(row['overall_rank'])}", 
                va='center', fontweight='bold')
    
    # Add individual metric ranks as text
    for i, (_, row) in enumerate(plot_df.iterrows()):
        metric_text = f"GM Yes: #{int(row['geometric_mean_yes_rank'])} | GM No: #{int(row['geometric_mean_no_rank'])} | Pearson: #{int(row['pearson_rank'])}"
        ax.text(0.5, i, metric_text, va='center', ha='left', fontsize=9, color='darkblue')
    
    # Set title and labels
    ax.set_title("Combined Model Ranking Across Multiple Metrics", fontsize=16)
    ax.set_xlabel("Combined Score (lower is better)", fontsize=12)
    ax.set_ylabel("Model", fontsize=12)
    
    # Invert y-axis to have the best model at the top
    ax.invert_yaxis()
    
    # Adjust layout
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(os.path.join(OUTPUT_DIR, "combined_ranking.png"))
    plt.close()

def main():
    # Load the combined metrics
    metrics_data = load_combined_metrics()
    
    # Extract and calculate balanced metrics
    model_metrics = extract_model_metrics(metrics_data)
    
    # Create DataFrame for visualization
    df = create_model_comparison_dataframe(model_metrics)
    
    # Save the processed metrics
    with open(os.path.join(OUTPUT_DIR, "processed_metrics.json"), 'w') as f:
        json.dump(model_metrics, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.float32, np.float64)) else x)
    
    # Create visualizations
    
    # 1. Model comparison by geometric mean for "yes" class
    plot_model_comparison(df, "geometric_mean_yes", "Model Comparison by Geometric Mean (Factual Class)")
    
    # 2. Model comparison by geometric mean for "no" class
    plot_model_comparison(df, "geometric_mean_no", "Model Comparison by Geometric Mean (Non-Factual Class)")
    
    # 3. Model comparison by F1 score for "yes" class
    plot_model_comparison(df, "f1_score_yes", "Model Comparison by F1 Score (Factual Class)")
    
    # 4. Model comparison by Pearson correlation
    plot_model_comparison(df, "pearson", "Model Comparison by Pearson Correlation")
    
    # 5. Dataset comparison by geometric mean for "yes" class
    plot_dataset_comparison(df, "geometric_mean_yes")
    
    # 6. Dataset comparison by geometric mean for "no" class
    plot_dataset_comparison(df, "geometric_mean_no")
    
    # 7. Correlation between geometric mean and binary accuracy
    plot_metric_correlation(df, "geometric_mean_no", "pearson")
    
    # 8. Correlation between geometric mean and Pearson correlation
    plot_metric_correlation(df, "geometric_mean_yes", "pearson")
    
    # 9. Radar chart for top models
    plot_radar_chart(df)
    
    # 10. Create summary table
    summary_df = create_summary_table(df)
    
    # 11. Create combined ranking based on multiple metrics
    ranking_df = create_combined_ranking(df)
    
    # 12. Plot combined ranking
    plot_combined_ranking(ranking_df)
    
    print(f"Visualizations saved to {OUTPUT_DIR}/")
    print(f"Summary table saved to {OUTPUT_DIR}/model_performance_summary.csv")
    print(f"Combined ranking saved to {OUTPUT_DIR}/model_combined_ranking.csv")
    
    # Print top 5 models by geometric mean
    print("\nTop 5 Models by Geometric Mean (Factual Class):")
    top_5 = summary_df.head(5)[["model", "geometric_mean_yes", "geometric_mean_no", "f1_score_yes", "pearson"]]
    print(top_5.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    
    # Print top 5 models by combined ranking
    print("\nTop 5 Models by Combined Ranking:")
    top_5_combined = ranking_df.head(5)[["model", "overall_rank", "combined_score", 
                                        "geometric_mean_yes", "geometric_mean_no", "pearson"]]
    print(top_5_combined.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

if __name__ == "__main__":
    main()
