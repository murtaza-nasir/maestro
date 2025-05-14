#!/bin/bash

# Default model if none provided
MODEL=${1:-"anthropic/claude-3.7-sonnet"}

echo "Testing API call to model: $MODEL"
python test_api_call.py "$MODEL"
