# Qwen 3 32B Example Reports

Qwen 3 32B offers an excellent balance of quality and performance, making it ideal for general research tasks and creative writing.

!!! info "Model Details"
    - **Parameters:** 32 Billion
    - **Context:** 150K tokens
    - **Deployment:** Self-hosted via vLLM
    - **Best For:** General research, business reports, travel guides

## Available Reports

<div class="grid cards" markdown>

-   **Nostalgia as Strategic Driver**
    
    ---
    
    **Style:** Business psychology analysis  
    **Length:** ~4,500 words
    
    Consumer behavior, economic uncertainty, and marketing strategy insights.
    
    [:octicons-arrow-right-24: Read Report](nostalgia-consumer-behavior.md)

-   **Nostalgia Typology Cross-Cultural**
    
    ---
    
    **Style:** Academic analysis  
    **Length:** ~8,000 words
    
    Cultural differences, socioeconomic factors, and decision psychology.
    
    [:octicons-arrow-right-24: Read Report](nostalgia-typology-cross-cultural.md)

-   **Satellite Night-Light Economic Analysis**
    
    ---
    
    **Style:** Technical methodology  
    **Length:** ~14,600 words
    
    Remote sensing data for consumer spending prediction with statistical validation.
    
    [:octicons-arrow-right-24: Read Report](satellite-night-light-consumer-spending.md)

-   **Eastern Road Trip Itinerary**
    
    ---
    
    **Style:** Detailed travel guide  
    **Length:** ~7,300 words
    
    Complete 14-day itinerary with budget estimates and local recommendations.
    
    [:octicons-arrow-right-24: Read Report](eastern-road-trip-detailed.md)

-   **A Royal Road Trip**
    
    ---
    
    **Style:** Pompous royal prose  
    **Length:** ~12,400 words
    
    Luxury travel experience with elaborate descriptions and premium recommendations.
    
    [:octicons-arrow-right-24: Read Report](royal-road-trip.md)

</div>

## Model Performance

### Strengths
- **Balanced Performance:** Good quality without excessive resource usage
- **Versatile Output:** Handles various styles effectively
- **Efficient Processing:** Faster than larger models  
- **Reliable Structure:** Consistent formatting and organization
- **Context Management:** Maintains coherence across long documents

### Best Use Cases
- General research and analysis
- Business reports and documentation
- Travel planning and guides
- Consumer behavior studies
- Cross-cultural analyses

### Deployment Configuration

```bash
python -m vllm.entrypoints.openai.api_server \
    --model "/path/to/model/Qwen_Qwen3-32B-AWQ" \
    --tensor-parallel-size 4 \
    --port 5000 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.90 \
    --served-model-name "localmodel" \
    --disable-log-requests \
    --disable-custom-all-reduce \
    --enable-prefix-caching \
    --guided-decoding-backend "xgrammar" \
    --chat-template /path/to/model/qwen3_nonthinking.jinja
```

### Hardware Requirements

!!! info "Resource Usage"
    - **Minimum:** 2x RTX 3090 (48GB VRAM)
    - **Recommended:** 4x RTX 3090 (96GB VRAM)
    - **Quantization:** AWQ 4-bit for consumer GPUs