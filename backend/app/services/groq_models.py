"""
Groq model configuration and selection logic.

Models are read from environment variables with sensible defaults.
When Groq deprecates a model, update the .env file in one place —
no code changes needed.
"""

import os
from typing import Optional, Literal
from enum import Enum


class ModelCategory(str, Enum):
    CLASSIFY = "classify"
    GRADE_FAST = "grade_fast"
    GRADE_REASONING = "grade_reasoning"
    VISION = "vision"
    VERIFY = "verify"


# Active Groq models (verified 2026-08-31)
DEFAULT_MODELS = {
    "GROQ_MODEL_CLASSIFY": "openai/gpt-oss-20b",  # Fast/cheap classification
    "GROQ_MODEL_GRADE_FAST": "openai/gpt-oss-20b",  # Fast text grading
    "GROQ_MODEL_GRADE_REASONING": "openai/gpt-oss-120b",  # Powerful reasoning for complex submissions
    "GROQ_MODEL_VISION": "",  # Empty = disabled (no vision models currently available on this account)
    "GROQ_MODEL_VERIFY": "openai/gpt-oss-20b",  # Fast/cheap assignment relevance verification
}


def get_model(category: ModelCategory) -> str:
    """
    Retrieve model ID for a given category from environment or defaults.
    
    Args:
        category: One of classify, grade_fast, grade_reasoning, vision
    
    Returns:
        Model ID string (e.g. "openai/gpt-oss-20b")
    
    Raises:
        ValueError: If vision model requested but not configured
    """
    env_key_map = {
        ModelCategory.CLASSIFY: "GROQ_MODEL_CLASSIFY",
        ModelCategory.GRADE_FAST: "GROQ_MODEL_GRADE_FAST",
        ModelCategory.GRADE_REASONING: "GROQ_MODEL_GRADE_REASONING",
        ModelCategory.VISION: "GROQ_MODEL_VISION",
        ModelCategory.VERIFY: "GROQ_MODEL_VERIFY",
    }
    
    env_key = env_key_map[category]
    model = os.getenv(env_key, DEFAULT_MODELS.get(env_key, ""))
    
    if not model:
        if category == ModelCategory.VISION:
            raise ValueError(
                f"Vision model not configured. Set {env_key} in .env or "
                "skip vision-capable submissions until a vision model is available on this Groq account."
            )
        raise ValueError(f"Model not configured: {env_key}")
    
    return model


def select_grading_model(
    classification: dict,
) -> str:
    """
    Select the grading model based on classification results.
    
    Logic:
    - simple submissions → fast model (cheaper, faster)
    - moderate/complex submissions → reasoning model (better analysis)
    - If images present but vision disabled → still use text model with warning flag
    
    Args:
        classification: Dict with keys: content_type, domain, complexity
            Example: {
                "content_type": "code",
                "domain": "computer_science",
                "complexity": "complex"
            }
    
    Returns:
        Model ID string
    """
    complexity = classification.get("complexity", "moderate")
    
    if complexity == "simple":
        return get_model(ModelCategory.GRADE_FAST)
    elif complexity in ("moderate", "complex"):
        return get_model(ModelCategory.GRADE_REASONING)
    else:
        return get_model(ModelCategory.GRADE_FAST)


def should_use_vision_for_content(content_type: str) -> bool:
    """
    Check if content_type should trigger vision model (and if one is available).
    
    Args:
        content_type: One of "code", "document_with_images", "text_document", "mixed"
    
    Returns:
        True if vision model should be used (and is configured), False otherwise
    """
    if content_type not in ("document_with_images", "mixed"):
        return False
    
    try:
        get_model(ModelCategory.VISION)
        return True
    except ValueError:
        # Vision model not configured
        return False
