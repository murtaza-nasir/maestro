# GPT-OSS 20B Example Reports

The smallest model in the GPT-OSS family, offering good performance for routine research tasks with excellent speed and efficiency.

!!! info "Model Details"
    - **Parameters:** 20 Billion
    - **Context:** 131K tokens
    - **Deployment:** Self-hosted via vLLM
    - **Best For:** Quick research, drafts, routine documentation

!!! warning "Known Issues"
    - **Instruction Following:** Difficulties with complex or non-traditional report formats

## Available Reports

<div class="grid cards" markdown>

-   **Psychological Effects of AI Tutoring**
    
    ---
    
    **Style:** Academic psychological research  
    **Length:** ~18,000 words
    
    AI education impacts, empirical analysis, and long-term effects.
    
    [:octicons-arrow-right-24: Read Report](psychological-effects-ai-tutoring.md)

-   **Neuro-Pricing Insights**
    
    ---
    
    **Style:** Technical business analysis  
    **Length:** ~17,000 words
    
    Neuroscience-based pricing models and implementation strategies.
    
    [:octicons-arrow-right-24: Read Report](neuro-pricing-insights.md)

-   **Surveillance in Hybrid Work**
    
    ---
    
    **Style:** Professional workplace analysis  
    **Length:** ~14,000 words
    
    Remote monitoring, privacy governance, and performance management.
    
    [:octicons-arrow-right-24: Read Report](surveillance-hybrid-work.md)

</div>

## Model Performance

### Strengths
- **Fast Generation:** Excellent speed for quick research
- **Resource Efficient:** Runs on modest hardware
- **Good Structure:** Maintains logical organization
- **Reliable Output:** Consistent quality for standard tasks
- **Cost Effective:** Minimal resource requirements

### Best Use Cases
- Quick research summaries
- Initial drafts and outlines
- Standard business reports
- Routine documentation
- Time-sensitive research tasks

### Deployment Configuration

```bash
python -m vllm.entrypoints.openai.api_server \
    --model "/path/to/model/openai_gpt-oss-20b" \
    --tensor-parallel-size 4 \
    --port 5000 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.9 \
    --served-model-name "localmodel" \
    --disable-log-requests \
    --disable-custom-all-reduce \
    --guided-decoding-backend "xgrammar"
```

### Hardware Requirements

!!! success "Resource Efficient"
    - **Minimum:** 1x RTX 3090 (24GB VRAM)
    - **Recommended:** 2x RTX 3090 (48GB VRAM)
    - **Actual Usage:** ~25GB VRAM