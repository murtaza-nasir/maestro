# DeepSeek V3 Example Reports

DeepSeek V3 is a state-of-the-art Mixture-of-Experts model with 671B total parameters (37B activated).

!!! info "Model Details"
    - **Parameters:** 671B total, 37B activated per token
    - **Context:** 128K tokens  
    - **Architecture:** Multi-head Latent Attention (MLA) + MoE
    - **Best For:** Complex reasoning, technical analysis, business strategy

## Available Reports

<div class="grid cards" markdown>

-   **Generative AI Skills Curriculum**
    
    ---
    
    **Style:** Strategic business education  
    **Length:** Comprehensive 16-week program
    
    Bridging the AI skills gap with a structured curriculum for business analytics professionals.
    
    [:octicons-arrow-right-24: Read Report](generative-ai-curriculum.md)

-   **Neurometrics to Optimal Pricing**
    
    ---
    
    **Style:** Technical economic analysis  
    **Length:** In-depth research paper
    
    Quantifying the shift from price-elastic to behavior-elastic demand using neuroscience insights.
    
    [:octicons-arrow-right-24: Read Report](neurometrics-pricing.md)

</div>

## Model Performance

### Best Use Cases
- Complex business strategy analysis
- Technical research papers
- Educational curriculum development
- Economic modeling and forecasting
- Multi-domain synthesis

### Key Innovations

The model introduces several groundbreaking features:

- **FP8 mixed precision** validated at extreme scale
- **14.8 trillion token** training corpus
- **2.788M H800 GPU hours** total training time

### Deployment Options

```python
# Via API (DeepSeek Platform)
# Pricing: $0.07-$0.56/M input tokens
#          $1.68/M output tokens

# Local deployment requires significant resources
# Recommended: Use via API for most applications
```

### Hardware Requirements

!!! warning "Resource Intensive"
    - **API Recommended:** Most cost-effective option
    - **Local Minimum:** 8x A100 80GB for FP8 inference
    - **Local Optimal:** Multi-node cluster for full performance