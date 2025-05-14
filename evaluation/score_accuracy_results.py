import pandas as pd
import numpy as np
import re
import sys
import os
import argparse
from collections import Counter

# Define the verifier models
VERIFIER_MODELS = [
    "qwen/qwen3-30b-a3b",
    "anthropic/claude-3.7-sonnet",
    "meta-llama/llama-4-maverick"
]

# Function to count references in a writing claim
def count_references(claim):
    # Look for patterns like [0041e6bf][32042cca][e2653dbc]
    references = re.findall(r'\[[a-f0-9]+\]', claim)
    return len(set(references))  # Count unique references

# Function to calculate score based on verification result and stage
def calculate_score(row):
    if row['verification_result'] == 'error':
        return 0  # Skip errors
    
    if row['stage'] == 'note':
        # For notes: yes = +1, partial = 0.5, no = -1
        if row['verification_result'] == 'yes':
            return 1
        elif row['verification_result'] == 'partial':
            return 0.5
        elif row['verification_result'] == 'no':
            return -1
    
    elif row['stage'] == 'writing':
        # Count references in the claim
        num_refs = count_references(row['claim'])
        
        if num_refs <= 1:  # Single or no reference
            # Use normal points
            if row['verification_result'] == 'yes':
                return 1
            elif row['verification_result'] == 'partial':
                return 0.5
            elif row['verification_result'] == 'no':
                return -1
        else:  # Multiple references
            if row['verification_result'] == 'yes':
                return 1
            elif row['verification_result'] == 'partial':
                # 1/n for every partial if there are n references
                return 1/num_refs
            elif row['verification_result'] == 'no':
                return -1
    
    return 0  # Default case

# Function to aggregate scores from multiple verifiers
def aggregate_scores(group):
    """
    Aggregates scores from multiple verifiers by summing them.
    This approach combines all verifier scores at the lowest level.
    """
    # Sum the scores across all verifiers
    return group['score'].sum()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Score accuracy test results')
    parser.add_argument('input_file', help='Path to the accuracy report CSV file')
    parser.add_argument('--output_dir', default='evaluation/results', 
                        help='Directory to save output files (default: evaluation/results)')
    parser.add_argument('--verifier_models', nargs='+', default=VERIFIER_MODELS,
                        help=f'List of verifier models to use (default: {VERIFIER_MODELS})')
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load the data
    print(f"Loading data from {args.input_file}")
    df = pd.read_csv(args.input_file)
    
    # Check if 'verifier_model' column exists, if not, assume it's from the old format
    if 'verifier_model' not in df.columns:
        print("Input file doesn't have 'verifier_model' column. Assuming all results are from a single verifier.")
        # Add a verifier_model column with a default value
        df['verifier_model'] = args.verifier_models[0]
    
    # Filter to include only the specified verifier models
    df = df[df['verifier_model'].isin(args.verifier_models)]
    
    # Apply scoring function to each row
    df['score'] = df.apply(calculate_score, axis=1)
    
    # Create a unique identifier for each verification task
    df['verification_task'] = df['llm'] + '_' + df['question'] + '_' + df['stage'] + '_' + df['context_index'].astype(str) + '_' + df['claim']
    
    # Instead of creating an aggregated dataframe with averaged scores,
    # we'll directly create an aggregated version by combining all verifier data
    
    # Create a copy of the dataframe with only the verifier data
    verifier_df = df.copy()
    
    # Create a new dataframe for the aggregated results
    aggregated_df = pd.DataFrame()
    
    # Group by llm and stage to get all unique combinations
    for (llm, stage), group in verifier_df.groupby(['llm', 'stage']):
        # Create a new row for the aggregated data
        agg_row = {
            'llm': llm,
            'stage': stage,
            'question': 'aggregated',  # Placeholder
            'context_index': -1,       # Placeholder
            'claim': 'aggregated',     # Placeholder
            'verification_result': 'aggregated_score',
            'verifier_model': 'aggregated',
            'score': group['score'].sum(),  # Sum all scores
            'verification_task': f"{llm}_{stage}_aggregated"  # Create a unique task ID
        }
        
        # Add to the aggregated dataframe
        aggregated_df = pd.concat([aggregated_df, pd.DataFrame([agg_row])], ignore_index=True)
    
    # Combine original and aggregated results
    combined_df = pd.concat([df, aggregated_df], ignore_index=True)
    
    # Create summaries for each verifier model
    all_summaries = []
    
    # Process each verifier model separately
    for verifier_model in combined_df['verifier_model'].unique():
        verifier_df = combined_df[combined_df['verifier_model'] == verifier_model]
        
        # Special handling for 'aggregated' verifier model
        if verifier_model == 'aggregated':
            # For aggregated results, we need to calculate the total samples differently
            # First, get the original data (excluding aggregated results)
            original_df = df.copy()
            
            # Create a summary dataframe with scores by LLM and stage
            # For aggregated results, we sum up all scores and counts from all verifiers
            summary_data = []
            
            # Process each LLM and stage combination
            for (llm, stage), group in original_df.groupby(['llm', 'stage']):
                # Get the corresponding row from the aggregated results
                agg_row = verifier_df[(verifier_df['llm'] == llm) & (verifier_df['stage'] == stage)]
                
                if not agg_row.empty:
                    # Calculate the total number of samples across all verifiers
                    total_samples = len(group)
                    
                    # Get the total score from the aggregated results
                    total_score = agg_row['score'].iloc[0]
                    
                    # Calculate the normalized score
                    normalized_score = total_score / total_samples if total_samples > 0 else 0
                    
                    # Add to summary data
                    summary_data.append({
                        'llm': llm,
                        'stage': stage,
                        'total_score': total_score,
                        'num_samples': total_samples,
                        'normalized_score': normalized_score,
                        'verifier_model': 'aggregated'
                    })
            
            # Convert to DataFrame
            summary = pd.DataFrame(summary_data)
            
            # Create overall summary for each LLM
            overall_data = []
            
            # Process each LLM with balanced weighting between note and writing
            for llm_name in original_df['llm'].unique():
                # Get all data for this LLM
                llm_group = original_df[original_df['llm'] == llm_name]
                
                # Get note and writing data separately
                note_data = llm_group[llm_group['stage'] == 'note']
                writing_data = llm_group[llm_group['stage'] == 'writing']
                
                # Calculate normalized scores for each stage
                note_score = note_data['score'].sum()
                note_samples = len(note_data)
                note_normalized = note_score / note_samples if note_samples > 0 else 0
                
                writing_score = writing_data['score'].sum()
                writing_samples = len(writing_data)
                writing_normalized = writing_score / writing_samples if writing_samples > 0 else 0
                
                # Calculate balanced overall score (50-50 weight)
                balanced_normalized_score = (note_normalized + writing_normalized) / 2
                
                # Calculate total score and samples (for reference)
                total_score = note_score + writing_score
                total_samples = note_samples + writing_samples
                
                # Add to overall data
                overall_data.append({
                    'llm': llm_name,  # Use the string value directly
                    'stage': 'overall',
                    'total_score': total_score,
                    'num_samples': total_samples,
                    'normalized_score': balanced_normalized_score,  # Use the balanced score
                    'verifier_model': 'aggregated'
                })
            
            # Convert to DataFrame
            overall = pd.DataFrame(overall_data)
        else:
            # For individual verifier models, use the standard approach
            # Create a summary dataframe with scores by LLM and stage
            summary = verifier_df.groupby(['llm', 'stage'])['score'].agg(['sum', 'count', 'mean']).reset_index()
            summary.rename(columns={'sum': 'total_score', 'count': 'num_samples', 'mean': 'normalized_score'}, inplace=True)
            summary['verifier_model'] = verifier_model
            
            # Create a summary for overall scores by LLM
            # Use a different approach to avoid tuple formatting issues
            overall_data = []
            
            # Process each unique LLM with balanced weighting
            for llm_name in verifier_df['llm'].unique():
                # Get all data for this LLM
                llm_data = verifier_df[verifier_df['llm'] == llm_name]
                
                # Get note and writing data separately
                note_data = llm_data[llm_data['stage'] == 'note']
                writing_data = llm_data[llm_data['stage'] == 'writing']
                
                # Calculate normalized scores for each stage
                note_score = note_data['score'].sum() if not note_data.empty else 0
                note_samples = len(note_data)
                note_normalized = note_score / note_samples if note_samples > 0 else 0
                
                writing_score = writing_data['score'].sum() if not writing_data.empty else 0
                writing_samples = len(writing_data)
                writing_normalized = writing_score / writing_samples if writing_samples > 0 else 0
                
                # Calculate balanced overall score (50-50 weight)
                balanced_normalized_score = (note_normalized + writing_normalized) / 2
                
                # Calculate total score and samples (for reference)
                total_score = note_score + writing_score
                num_samples = note_samples + writing_samples
                
                # Add to overall data
                overall_data.append({
                    'llm': llm_name,
                    'stage': 'overall',
                    'total_score': total_score,
                    'num_samples': num_samples,
                    'normalized_score': balanced_normalized_score,  # Use the balanced score
                    'verifier_model': verifier_model
                })
            
            # Convert to DataFrame
            overall = pd.DataFrame(overall_data)
        
        # Combine the summaries
        verifier_summary = pd.concat([summary, overall])
        all_summaries.append(verifier_summary)
    
    # Combine all summaries
    if not all_summaries:
        print(f"Error: No data found for the specified verifier models: {args.verifier_models}", file=sys.stderr)
        print(f"Please check if the input file '{args.input_file}' contains entries for these models in the 'verifier_model' column, or specify different models using --verifier_models.", file=sys.stderr)
        sys.exit(1)
    final_summary = pd.concat(all_summaries, ignore_index=True)
    
    # Get base filename without extension for output files
    input_basename = os.path.basename(args.input_file)
    input_name = os.path.splitext(input_basename)[0]
    
    # Define output file paths
    detailed_scores_path = os.path.join(args.output_dir, f"{input_name}_detailed_scores.csv")
    summary_path = os.path.join(args.output_dir, f"{input_name}_summary.csv")
    
    # Save the detailed scores
    combined_df[['llm', 'question', 'stage', 'context_index', 'verification_result', 'score', 'verifier_model']].to_csv(
        detailed_scores_path, index=False)
    
    # Save the summary scores
    final_summary.to_csv(summary_path, index=False)
    
    print(f"Scoring complete. Results saved to:")
    print(f"  - {detailed_scores_path}")
    print(f"  - {summary_path}")
    
    # Print a summary of the aggregated results
    if 'aggregated' in final_summary['verifier_model'].unique():
        agg_summary = final_summary[final_summary['verifier_model'] == 'aggregated']
        print("\nAggregated Results Summary:")
        print(agg_summary[['llm', 'stage', 'total_score', 'num_samples', 'normalized_score']])

if __name__ == "__main__":
    main()
