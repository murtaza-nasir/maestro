import re
from collections import defaultdict
import ai_researcher.config as config # <-- Import config


# --- Option 2: Read from a file (uncomment the lines below) ---
log_file_path = 'streamlit_app.log' # <--- CHANGE THIS TO YOUR FILE NAME
try:
    with open(log_file_path, 'r') as f:
        log_data = f.read()
except FileNotFoundError:
    print(f"Error: File not found at '{log_file_path}'")
    log_data = "" # Ensure log_data is defined even if file is not found

# Use defaultdict for easy aggregation. The default value for a new key will be 0.0
model_costs = defaultdict(float)
total_cost = 0.0
web_search_count = 0 # <-- Initialize web search counter

# Regex to find the lines with cost information and extract model name and cost value
# Explanation:
# - "Calculated cost for ": Matches the literal text start
# - "(.*?)": Captures the model name (non-greedy match) - Group 1
# - ": ": Matches the colon and space separator
# - "\$": Matches the literal dollar sign
# - "([\d.]+)": Captures the cost value (one or more digits or periods) - Group 2
cost_pattern = re.compile(r"Calculated cost for (.*?): \$([\d.]+)")
# Pattern to find the web search increment log line
web_search_pattern = "Successfully called increment_web_search_count"

# Process each line in the log data
for line in log_data.strip().split('\n'):
    cost_match = cost_pattern.search(line)
    if cost_match:
        model_name = cost_match.group(1).strip()  # Extract model name from group 1
        cost_str = cost_match.group(2)          # Extract cost string from group 2
        try:
            cost = float(cost_str)
            model_costs[model_name] += cost  # Add cost to the model's total
            total_cost += cost               # Add cost to the overall total
        except ValueError:
            # This handles cases where the captured cost isn't a valid number
            print(f"Warning: Could not parse cost '{cost_str}' from line: {line}")
    elif web_search_pattern in line: # <-- Check for web search log line
        web_search_count += 1        # <-- Increment counter

# --- Print the results ---
print("--- Cost Breakdown by Model ---")
if model_costs:
    # Sort models alphabetically for consistent output
    for model, cost in sorted(model_costs.items()):
        # Format cost to show several decimal places, adjust '6f' as needed
        print(f"- {model}: ${cost:.6f}")
    print("-" * 30)
    # Calculate and add web search cost
    total_web_search_cost = web_search_count * config.WEB_SEARCH_COST_PER_CALL
    total_cost += total_web_search_cost
    print(f"Web Searches: {web_search_count} calls @ ${config.WEB_SEARCH_COST_PER_CALL:.4f}/call = ${total_web_search_cost:.6f}")
    print("-" * 30)
    print(f"Total Calculated Cost (Models + Web Search): ${total_cost:.6f}")
else:
    # Check if only web searches were found
    if web_search_count > 0:
        total_web_search_cost = web_search_count * config.WEB_SEARCH_COST_PER_CALL
        total_cost += total_web_search_cost
        print("--- Cost Breakdown by Model ---")
        print("No model cost lines found.")
        print("-" * 30)
        print(f"Web Searches: {web_search_count} calls @ ${config.WEB_SEARCH_COST_PER_CALL:.4f}/call = ${total_web_search_cost:.6f}")
        print("-" * 30)
        print(f"Total Calculated Cost (Models + Web Search): ${total_cost:.6f}")
    else:
        print("No cost information lines (models or web searches) were found in the log data.")
