import os
import json
import sys
import glob
from pprint import pprint

def inspect_raw_responses(model_name=None):
    """Inspect raw responses from evaluation runs."""
    results_dir = "verifier_results/debug"
    
    if not os.path.exists(results_dir):
        print(f"Error: Debug directory '{results_dir}' not found.")
        return
    
    # Find all raw response files
    if model_name:
        model_filename = model_name.replace("/", "_").replace("-", "_")
        response_files = glob.glob(os.path.join(results_dir, f"{model_filename}_raw_responses.txt"))
    else:
        response_files = glob.glob(os.path.join(results_dir, "*_raw_responses.txt"))
    
    if not response_files:
        print(f"No raw response files found for {'model ' + model_name if model_name else 'any model'}.")
        return
    
    for file_path in response_files:
        model = os.path.basename(file_path).replace("_raw_responses.txt", "")
        print(f"\n=== Raw responses for {model} ===\n")
        
        with open(file_path, 'r') as f:
            content = f.read()
            print(content[:2000])  # Print first 2000 chars to avoid overwhelming output
            print("...\n(truncated)")

def inspect_json_results(model_name=None):
    """Inspect JSON evaluation results."""
    results_dir = "verifier_results"
    
    if not os.path.exists(results_dir):
        print(f"Error: Results directory '{results_dir}' not found.")
        return
    
    # Find all JSON result files
    if model_name:
        model_filename = model_name.replace("/", "_").replace("-", "_")
        json_files = glob.glob(os.path.join(results_dir, f"{model_filename}_evaluations.json"))
    else:
        json_files = glob.glob(os.path.join(results_dir, "*_evaluations.json"))
    
    if not json_files:
        print(f"No JSON result files found for {'model ' + model_name if model_name else 'any model'}.")
        return
    
    for file_path in json_files:
        model = os.path.basename(file_path).replace("_evaluations.json", "")
        print(f"\n=== JSON results for {model} ===\n")
        
        with open(file_path, 'r') as f:
            data = json.load(f)
            # Print summary statistics
            verification_results = [item.get('verification_result') for item in data if item.get('verification_result')]
            result_counts = {}
            for result in verification_results:
                result_counts[result] = result_counts.get(result, 0) + 1
            
            print(f"Total samples: {len(data)}")
            print(f"Successful evaluations: {len(verification_results)}")
            print(f"Failed evaluations: {len(data) - len(verification_results)}")
            print("\nVerification result distribution:")
            for result, count in result_counts.items():
                print(f"  {result}: {count} ({count/len(data)*100:.1f}%)")
            
            # Print a few sample results
            print("\nSample results:")
            for i, item in enumerate(data[:5]):  # Show first 5 results
                print(f"\nSample {i+1}:")
                print(f"  Verification result: {item.get('verification_result')}")
                print(f"  Factuality score: {item.get('factuality_score')}")
                print(f"  Human factuality: {item.get('human_factuality')}")

def main():
    """Main function to inspect evaluation results."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Inspect verifier evaluation results")
    parser.add_argument("--model", help="Model name to inspect (e.g., 'anthropic/claude-3.7-sonnet')")
    parser.add_argument("--raw", action="store_true", help="Inspect raw responses")
    parser.add_argument("--json", action="store_true", help="Inspect JSON results")
    
    args = parser.parse_args()
    
    if args.raw or not (args.raw or args.json):
        inspect_raw_responses(args.model)
    
    if args.json or not (args.raw or args.json):
        inspect_json_results(args.model)

if __name__ == "__main__":
    main()
