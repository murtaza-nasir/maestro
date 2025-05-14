import json
import os
import time
import asyncio
import glob
import re
from typing import Dict, List, Any
import pandas as pd
import numpy as np
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from dotenv import load_dotenv

load_dotenv()

# Set up OpenRouter client with OpenAI compatibility in async mode
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY")
)

# Paths to CNN/Daily Mail dataset files
DATASET_DIR = "../datasets/cnn_dailymail"  # Update this to your local path
QUESTIONS_DIR = os.path.join(DATASET_DIR, "questions")  # Directory containing question files
SUBSET = "test"  # 'train', 'validation', or 'test'

# Define multiple models to compare
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
MAX_SAMPLES = 100  # Set to None to evaluate all samples
MAX_CONCURRENT_REQUESTS = 10  # Number of parallel requests per model
MAX_CONCURRENT_MODELS = 3     # Number of models to evaluate simultaneously
OUTPUT_DIR = "results/cnn_dailymail"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_cnn_dailymail_dataset(subset="test", max_samples=None):
    """Load the CNN/Daily Mail dataset for a specific subset."""
    data = []
    question_files = glob.glob(os.path.join(QUESTIONS_DIR, subset, "*.question"))
    
    if max_samples:
        question_files = question_files[:max_samples]
    
    print(f"Loading {len(question_files)} {subset} examples...")
    
    for file_path in tqdm(question_files):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip().split('\n\n')
                
                # Parse the file according to its format
                # Format: [URL]\n\n[Context]\n\n[Question]\n\n[Answer]\n\n[Entity mapping]
                if len(content) >= 4:  # Ensure we have at least URL, context, question, answer
                    url = content[0].strip()
                    context = content[1].strip()
                    question = content[2].strip()
                    answer = content[3].strip()
                    
                    # Extract entity mapping if available
                    entity_mapping = None
                    if len(content) > 4:
                        entity_mapping = content[4].strip()
                    
                    # Extract file ID from the file path
                    file_id = os.path.basename(file_path).replace('.question', '')
                    
                    data.append({
                        'id': file_id,
                        'url': url,
                        'context': context,
                        'question': question,
                        'answer': answer,
                        'entity_mapping': entity_mapping,
                    })
        except Exception as e:
            print(f"Error loading file {file_path}: {e}")
    
    print(f"Loaded {len(data)} examples from {subset} set")
    return data

async def evaluate_qa_performance(context: str, question: str, answer: str, model: str, 
                                 semaphore: asyncio.Semaphore = None) -> Dict[str, Any]:
    """
    Evaluate the model's ability to answer the question given the context.
    """
    prompt = f"""You are given a reading comprehension task. Read the context and answer the question based only on the information in the context.

Context:
{context}

Question:
{question}

Based on the context, provide your answer in the following JSON format:
{{
  "answer": "Your answer here"
}}

Your answer should be brief and precise, matching the style of the expected answer. Do not include any explanations or additional information.
"""

    try:
        # Use semaphore to limit concurrent requests if provided
        if semaphore:
            async with semaphore:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=512,
                    response_format={"type": "json_object"}
                )
        else:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=512,
                response_format={"type": "json_object"}
            )
        
        # Extract and parse the JSON response
        content = response.choices[0].message.content.strip()
        result = json.loads(content)
        
        model_answer = result.get("answer", "").strip()
        
        # Compare with ground truth answer
        # For CNN/Daily Mail, we need to normalize the answers for comparison
        correct = is_answer_correct(model_answer, answer)
        
        return {
            "model_answer": model_answer,
            "ground_truth": answer,
            "is_correct": correct,
            "raw_response": content
        }
    except Exception as e:
        print(f"Error in API call for model {model}: {e}")
        # Return a default value in case of error
        return {
            "model_answer": None,
            "ground_truth": answer,
            "is_correct": False,
            "raw_response": f"Error: {str(e)}"
        }

def is_answer_correct(model_answer, ground_truth):
    """
    Check if the model's answer is correct.
    For CNN/Daily Mail, the answers are entities, so we do a normalized comparison.
    """
    # Normalize both answers: lowercase, remove punctuation, trim spaces
    def normalize(text):
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        return text.strip()
    
    normalized_model = normalize(model_answer)
    normalized_truth = normalize(ground_truth)
    
    # Check exact match
    if normalized_model == normalized_truth:
        return True
    
    # Allow for partial match if the entity is a multi-word entity
    # This is a simplified approach - may need refinement based on dataset specifics
    if normalized_truth in normalized_model or normalized_model in normalized_truth:
        return True
    
    return False

async def evaluate_samples_for_model(model: str, dataset: List, 
                                    max_concurrent: int = 10) -> List[Dict]:
    """Evaluate all samples for a given model in parallel batches."""
    model_results = []
    tasks = []
    semaphore = asyncio.Semaphore(max_concurrent)
    
    model_short_name = model.split('/')[-1]
    print(f"\nEvaluating {len(dataset)} samples with {model_short_name} in parallel...")
    
    # Create all tasks
    for i, item in enumerate(dataset):
        context = item['context']
        question = item['question']
        answer = item['answer']
        
        task = asyncio.create_task(evaluate_qa_performance(context, question, answer, model, semaphore))
        tasks.append((i, item['id'], task))
    
    # Process results as they complete
    for i, sample_id, task in async_tqdm(tasks, desc=f"Processing {model_short_name}"):
        evaluation = await task
        
        model_results.append({
            "id": sample_id,
            "sample_index": i,
            "model": model,
            "question": dataset[i]['question'],
            "context": dataset[i]['context'],
            "ground_truth": evaluation["ground_truth"],
            "model_answer": evaluation["model_answer"],
            "is_correct": evaluation["is_correct"]
        })
    
    return model_results

def compute_metrics(model_results):
    """Compute performance metrics for model predictions."""
    # Filter out any None values
    valid_results = [r for r in model_results if r["model_answer"] is not None]
    
    if len(valid_results) < 1:
        return {
            "accuracy": None,
            "samples_evaluated": 0
        }
    
    # Calculate accuracy
    correct_count = sum(1 for r in valid_results if r["is_correct"])
    accuracy = correct_count / len(valid_results)
    
    return {
        "accuracy": accuracy,
        "samples_evaluated": len(valid_results)
    }

def create_comparison_visualizations(all_models_results, comparison_metrics):
    """Create visualizations comparing the performance of different models."""
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # 1. Create a bar chart comparing accuracy
        plt.figure(figsize=(15, 8))
        
        models = list(comparison_metrics.keys())
        model_short_names = [model.split('/')[-1] for model in models]
        accuracies = [comparison_metrics[model]['accuracy'] * 100 for model in models]
        
        x = np.arange(len(models))
        
        plt.bar(x, accuracies, width=0.6, color='skyblue')
        
        plt.xlabel('Models')
        plt.ylabel('Accuracy (%)')
        plt.title('Model Accuracy on CNN/Daily Mail Dataset')
        plt.xticks(x, model_short_names, rotation=45, ha='right')
        plt.ylim(0, 100)
        
        # Add accuracy values on top of bars
        for i, v in enumerate(accuracies):
            plt.text(i, v + 1, f"{v:.1f}%", ha='center')
        
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "model_accuracy_comparison.png"))
        
        # 2. Create a table with all metrics
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.axis('tight')
        ax.axis('off')
        
        table_data = []
        for model in models:
            metrics = comparison_metrics[model]
            model_name = model.split('/')[-1]
            row = [
                model_name,
                f"{metrics['accuracy']*100:.2f}%",
                f"{metrics['samples_evaluated']}"
            ]
            table_data.append(row)
        
        table = ax.table(
            cellText=table_data,
            colLabels=['Model', 'Accuracy', 'Samples Evaluated'],
            loc='center',
            cellLoc='center'
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        plt.title('Detailed Performance Metrics on CNN/Daily Mail Dataset')
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "model_performance_table.png"))
        
        print("Comparison visualizations created successfully.")
    except ImportError:
        print("Required visualization libraries not installed. Skipping visualizations.")
        print("Try: pip install matplotlib seaborn")
    except Exception as e:
        print(f"Error creating visualizations: {e}")

async def evaluate_models_in_parallel(dataset, 
                                     max_concurrent_requests=10, 
                                     max_concurrent_models=3):
    """Evaluate multiple models in parallel."""
    all_models_results = {}
    comparison_metrics = {}
    
    # Process models in batches to avoid too many concurrent connections
    for i in range(0, len(MODELS), max_concurrent_models):
        model_batch = MODELS[i:i+max_concurrent_models]
        
        # Create tasks for each model in this batch
        tasks = {model: evaluate_samples_for_model(model, dataset, max_concurrent_requests) 
                for model in model_batch}
        
        # Wait for all models in this batch to complete
        for model, task in tasks.items():
            model_results = await task
            
            # Save detailed results for this model
            model_filename = model.replace("/", "_").replace("-", "_")
            with open(os.path.join(OUTPUT_DIR, f"{model_filename}_evaluations.json"), 'w') as f:
                json.dump(model_results, f, indent=2)
            
            # Create DataFrame for analysis
            df = pd.DataFrame(model_results)
            df.to_csv(os.path.join(OUTPUT_DIR, f"{model_filename}_evaluations.csv"), index=False)
            
            # Compute metrics for this model
            metrics = compute_metrics(model_results)
            
            # Save metrics for this model
            with open(os.path.join(OUTPUT_DIR, f"{model_filename}_metrics.json"), 'w') as f:
                json.dump(metrics, f, indent=2)
            
            # Store results and metrics for comparison
            all_models_results[model] = model_results
            comparison_metrics[model] = metrics
            
            # Print summary for this model
            model_short_name = model.split('/')[-1]
            print(f"\nEvaluation Results for {model_short_name}:")
            print(f"Samples evaluated: {metrics['samples_evaluated']}")
            print(f"Accuracy: {metrics['accuracy']*100:.2f}%")
            
            # Generate additional analysis
            if model_results:
                correct = [r for r in model_results if r["is_correct"]]
                incorrect = [r for r in model_results if not r["is_correct"] and r["model_answer"] is not None]
                
                print(f"Correct answers: {len(correct)} ({len(correct)/len(model_results)*100:.1f}%)")
                print(f"Incorrect answers: {len(incorrect)} ({len(incorrect)/len(model_results)*100:.1f}%)")
                
                # Sample incorrect examples (up to 3) for analysis
                if incorrect:
                    print("\nSample incorrect predictions:")
                    for i, ex in enumerate(incorrect[:3]):
                        print(f"  Example {i+1}:")
                        print(f"    Question: {ex['question']}")
                        print(f"    Expected: {ex['ground_truth']}")
                        print(f"    Predicted: {ex['model_answer']}")
                        print()
    
    return all_models_results, comparison_metrics

async def main_async():
    print("Loading CNN/Daily Mail dataset...")
    dataset = load_cnn_dailymail_dataset(subset=SUBSET, max_samples=MAX_SAMPLES)
    
    if not dataset:
        print("Error: No data loaded. Please check the dataset path.")
        return
    
    print(f"Loaded {len(dataset)} samples from CNN/Daily Mail {SUBSET} set")
    
    # Evaluate all models with parallelism
    all_models_results, comparison_metrics = await evaluate_models_in_parallel(
        dataset, 
        max_concurrent_requests=MAX_CONCURRENT_REQUESTS,
        max_concurrent_models=MAX_CONCURRENT_MODELS
    )
    
    # Save comparison data
    with open(os.path.join(OUTPUT_DIR, "all_models_comparison.json"), 'w') as f:
        # Convert complex objects to serializable format
        serializable_metrics = {model: {k: (float(v) if isinstance(v, np.float64) else v) 
                                      for k, v in metrics.items()} 
                              for model, metrics in comparison_metrics.items()}
        json.dump(serializable_metrics, f, indent=2)
    
    # Create comparative visualizations
    create_comparison_visualizations(all_models_results, comparison_metrics)
    
    # Generate model rankings based on accuracy
    print("\nModel Rankings by Accuracy:")
    
    # Rank by accuracy
    accuracy_ranking = sorted([(model, metrics['accuracy']) for model, metrics in comparison_metrics.items()], 
                            key=lambda x: x[1] if x[1] is not None else -1, reverse=True)
    
    for i, (model, score) in enumerate(accuracy_ranking):
        print(f"{i+1}. {model.split('/')[-1]}: {score*100:.2f}%")

def main():
    """Synchronous entry point that runs the async main function."""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()