#!/usr/bin/env python3
"""
Test script for verifying OpenRouter pricing and token counting discrepancies.

This script helps diagnose why tracked costs in MAESTRO may differ from 
OpenRouter dashboard charges.

Usage:
    python scripts/test_openrouter_pricing.py --api-key YOUR_OPENROUTER_API_KEY

Requirements:
    pip install httpx
"""

import argparse
import asyncio
import httpx
import json
import sys
from typing import List, Dict, Any


# Known pricing for qwen3-next-80b-a3b-instruct (as of 2024)
DEFAULT_MODEL = "qwen/qwen3-next-80b-a3b-instruct"
PROMPT_PRICE_PER_M = 0.10  # $0.10 per 1M prompt tokens
COMPLETION_PRICE_PER_M = 0.80  # $0.80 per 1M completion tokens


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count (4 chars = ~1 token)"""
    return len(text) // 4


async def test_pricing_discrepancy(api_key: str, model: str = DEFAULT_MODEL):
    """
    Test OpenRouter's token counting and pricing to identify discrepancies.
    
    This test will:
    1. Make API calls with various prompt sizes
    2. Compare our calculated costs vs OpenRouter's reported costs
    3. Identify patterns in pricing discrepancies
    """
    
    print("=" * 80)
    print("OPENROUTER PRICING DISCREPANCY TEST")
    print("=" * 80)
    print(f"Testing model: {model}")
    print(f"Expected pricing: ${PROMPT_PRICE_PER_M}/1M prompt, ${COMPLETION_PRICE_PER_M}/1M completion")
    print()
    
    # Test cases with varying prompt lengths
    test_cases = [
        {
            "name": "Small prompt, small output",
            "messages": [
                {"role": "user", "content": "What is 2+2? Answer with just the number."}
            ],
            "max_tokens": 10
        },
        {
            "name": "Medium prompt, medium output",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain quantum computing in 50 words."}
            ],
            "max_tokens": 100
        },
        {
            "name": "Large prompt, small output",
            "messages": [
                {"role": "user", "content": "Read this text and summarize in one sentence: " + 
                 ("The advancement of artificial intelligence has transformed various industries. " * 50)}
            ],
            "max_tokens": 50
        },
        {
            "name": "Small prompt, large output",
            "messages": [
                {"role": "user", "content": "Write a detailed essay about climate change."}
            ],
            "max_tokens": 500
        }
    ]
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "MAESTRO Pricing Test"
        }
        
        results = []
        print("Running tests...\n")
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"Test {i}: {test_case['name']}")
            
            try:
                # Make API call with usage tracking enabled
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": test_case['messages'],
                        "max_tokens": test_case['max_tokens'],
                        "temperature": 0.7,
                        "usage": {
                            "include": True  # Enable usage tracking
                        }
                    }
                )
                response.raise_for_status()
                
                result = response.json()
                usage = result.get('usage', {})
                
                if usage:
                    # Extract token counts and costs
                    prompt_tokens = usage.get('prompt_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0)
                    reported_cost_credits = usage.get('cost', 0)
                    reported_cost_dollars = reported_cost_credits / 100
                    
                    # Calculate expected cost
                    calc_cost = (prompt_tokens * PROMPT_PRICE_PER_M + 
                                completion_tokens * COMPLETION_PRICE_PER_M) / 1_000_000
                    
                    # Store results
                    results.append({
                        "test": test_case['name'],
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "calculated_cost": calc_cost,
                        "api_reported_cost": reported_cost_dollars,
                        "discrepancy": reported_cost_dollars - calc_cost if calc_cost > 0 else 0
                    })
                    
                    print(f"  Tokens: {prompt_tokens} prompt, {completion_tokens} completion")
                    print(f"  Calculated cost: ${calc_cost:.6f}")
                    print(f"  API reported cost: ${reported_cost_dollars:.6f}")
                    
                    if calc_cost > 0:
                        ratio = reported_cost_dollars / calc_cost
                        if abs(ratio - 1) > 0.1:
                            print(f"  ⚠️  Discrepancy: {ratio:.2f}x")
                    print()
                    
                await asyncio.sleep(1)  # Rate limiting
                
            except Exception as e:
                print(f"  Error: {e}\n")
        
        # Generate summary report
        if results:
            print("=" * 80)
            print("SUMMARY REPORT")
            print("=" * 80)
            print()
            print("Test Results:")
            print("-" * 80)
            print(f"{'Test':<30} | {'Prompt':<7} | {'Compl':<7} | {'Calc Cost':<12} | {'API Cost':<12} | {'Diff':<10}")
            print("-" * 80)
            
            total_calc = 0
            total_api = 0
            
            for r in results:
                total_calc += r['calculated_cost']
                total_api += r['api_reported_cost']
                
                name = r['test'][:28]
                print(f"{name:<30} | {r['prompt_tokens']:>7} | {r['completion_tokens']:>7} | "
                      f"${r['calculated_cost']:>11.6f} | ${r['api_reported_cost']:>11.6f} | "
                      f"${r['discrepancy']:>+9.6f}")
            
            print("-" * 80)
            print(f"{'TOTAL':<30} | {'':>7} | {'':>7} | ${total_calc:>11.6f} | ${total_api:>11.6f} | "
                  f"${total_api - total_calc:>+9.6f}")
            
            print()
            print("Analysis:")
            print("-" * 40)
            
            if total_calc > 0:
                avg_ratio = total_api / total_calc
                print(f"Average discrepancy ratio: {avg_ratio:.2f}x")
                
                if avg_ratio < 0.1:
                    print("\n⚠️  ISSUE DETECTED: OpenRouter's usage.cost field appears broken")
                    print("The API is returning costs that are ~100x too low.")
                    print("This is likely a unit conversion issue (credits vs dollars).")
                elif avg_ratio > 1.2:
                    print("\n⚠️  ISSUE DETECTED: OpenRouter is charging more than advertised")
                    print(f"Actual charges are {(avg_ratio - 1) * 100:.1f}% higher than calculated.")
                elif 0.9 <= avg_ratio <= 1.1:
                    print("\n✅ Pricing appears consistent with advertised rates.")
                
            print()
            print("IMPORTANT NOTES:")
            print("-" * 40)
            print("1. OpenRouter's usage.cost field may be unreliable")
            print("2. Dashboard charges may not match advertised pricing")
            print("3. Token counts in API responses are generally accurate")
            print("4. Always compare with actual dashboard charges for verification")


def main():
    parser = argparse.ArgumentParser(
        description="Test OpenRouter pricing and token counting discrepancies"
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="Your OpenRouter API key"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to test (default: {DEFAULT_MODEL})"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(test_pricing_discrepancy(args.api_key, args.model))
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()