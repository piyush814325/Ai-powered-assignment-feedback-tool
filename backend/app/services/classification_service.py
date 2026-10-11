"""
Classification Service - Stage 1 of two-stage evaluation pipeline.

Classifies submissions by:
- Content type (code, text_document, document_with_images, mixed)
- Domain (computer_science, engineering, finance, medical, general)
- Complexity (simple, moderate, complex)
"""

import json
import httpx
import os
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
from app.services.groq_models import get_model, ModelCategory

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_REQUEST_TIMEOUT = 60


class ClassificationService:
    """Service for classifying submissions in Stage 1 of evaluation."""

    @staticmethod
    async def classify(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[str, str, str, float, Optional[list]]:
        """
        Classify a submission using fast Groq model.
        
        Args:
            text: Submission text content
            code: Code content if present
            rubric_criteria: List of evaluation criteria
        
        Returns:
            Tuple of (content_type, domain, complexity, confidence, issues)
            - content_type: "code", "text_document", "document_with_images", "mixed"
            - domain: "computer_science", "engineering", "finance", "medical", "general"
            - complexity: "simple", "moderate", "complex"
            - confidence: 0.0-1.0 classification confidence
            - issues: List of preliminary issues found (or None)
        """
        
        if not text and not code:
            return "text_document", "general", "simple", 0.5, None
        
        # Try real Groq classification first
        try:
            return await ClassificationService._groq_classify(text, code, rubric_criteria)
        except Exception as e:
            print(f"Classification failed: {e}. Using fallback.")
            return ClassificationService._fallback_classify(text, code, rubric_criteria)

    @staticmethod
    async def _groq_classify(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[str, str, str, float, Optional[list]]:
        """Classify using Groq API."""
        
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set")
        
        model = get_model(ModelCategory.CLASSIFY)
        prompt = ClassificationService._build_classification_prompt(text, code, rubric_criteria)
        
        try:
            async with httpx.AsyncClient(timeout=GROQ_REQUEST_TIMEOUT) as client:
                response = await client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,  # Lower temp for classification accuracy
                        "max_tokens": 1024
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text or f"HTTP {response.status_code}"
                    raise ValueError(f"Groq API error: {error_detail}")
                
                result = response.json()
                response_content = result["choices"][0]["message"]["content"]
                
                # Parse JSON response
                classification_data = json.loads(response_content)
                
                # Extract and validate fields
                content_type = classification_data.get("content_type", "text_document")
                domain = classification_data.get("domain", "general")
                complexity = classification_data.get("complexity", "moderate")
                confidence = float(classification_data.get("confidence", 0.7))
                issues = classification_data.get("issues")
                
                # Validate values
                valid_content_types = {"code", "text_document", "document_with_images", "mixed"}
                valid_domains = {"computer_science", "engineering", "finance", "medical", "general"}
                valid_complexities = {"simple", "moderate", "complex"}
                
                if content_type not in valid_content_types:
                    content_type = "text_document"
                if domain not in valid_domains:
                    domain = "general"
                if complexity not in valid_complexities:
                    complexity = "moderate"
                confidence = max(0.0, min(1.0, confidence))
                
                return content_type, domain, complexity, confidence, issues
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse classification JSON: {e}")
        except httpx.TimeoutException:
            raise ValueError("Classification request timed out")
        except httpx.RequestError as e:
            raise ValueError(f"Classification request failed: {e}")

    @staticmethod
    def _fallback_classify(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[str, str, str, float, Optional[list]]:
        """
        Fallback classification using heuristics when API fails.
        Analyzes submission characteristics to classify.
        """
        
        issues = []
        
        # Determine content type
        has_code = code and len(code.strip()) > 0
        has_text = text and len(text.strip()) > 0
        code_ratio = len(code or "") / (len(text or "") + len(code or "") + 1)
        
        if has_code and has_text:
            if code_ratio > 0.4:
                content_type = "mixed"
            else:
                content_type = "text_document"
        elif has_code:
            content_type = "code"
        else:
            content_type = "text_document"
        
        # Infer domain from content keywords
        domain = ClassificationService._infer_domain(text, code)
        
        # Estimate complexity from content length and detail
        text_len = len(text or "")
        code_len = len(code or "")
        total_len = text_len + code_len
        
        if total_len < 500:
            complexity = "simple"
        elif total_len < 2000:
            complexity = "moderate"
        else:
            complexity = "complex"
        
        # Check for simple issues
        if has_code and code and len(code.strip()) < 50:
            issues.append({
                "description": "Code submission is very brief",
                "severity": "warning"
            })
        
        if not has_text and not has_code:
            issues.append({
                "description": "No submission content found",
                "severity": "error"
            })
        
        return content_type, domain, complexity, 0.6, issues if issues else None

    @staticmethod
    def _infer_domain(text: str, code: Optional[str]) -> str:
        """Infer submission domain from keywords in content."""
        
        combined = (text or "") + " " + (code or "")
        combined_lower = combined.lower()
        
        # Domain-specific keywords
        cs_keywords = {"algorithm", "data structure", "class", "function", "def", "import", "array", "linked", "tree", "graph", "sort"}
        eng_keywords = {"circuit", "voltage", "current", "resistance", "force", "stress", "strain", "mechanical", "electrical", "structural"}
        finance_keywords = {"stock", "bond", "investment", "portfolio", "return", "risk", "dividend", "equity", "derivative", "hedge"}
        medical_keywords = {"patient", "disease", "treatment", "diagnosis", "symptom", "medicine", "clinical", "health", "medical", "virus"}
        
        scores = {
            "computer_science": sum(1 for kw in cs_keywords if kw in combined_lower),
            "engineering": sum(1 for kw in eng_keywords if kw in combined_lower),
            "finance": sum(1 for kw in finance_keywords if kw in combined_lower),
            "medical": sum(1 for kw in medical_keywords if kw in combined_lower),
        }
        
        # Return domain with highest score, default to general
        max_score = max(scores.values())
        if max_score > 0:
            for domain_name, score in scores.items():
                if score == max_score:
                    return domain_name
        return "general"

    @staticmethod
    def _build_classification_prompt(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> str:
        """Build prompt for classification stage."""
        
        rubric_summary = "\n".join([
            f"- {c.get('label', c.get('name', 'Unknown'))}: {c.get('description', '')}"
            for c in rubric_criteria[:5]  # First 5 criteria for context
        ])
        
        submission_section = f"SUBMISSION TEXT:\n{text[:1000]}"
        if code:
            submission_section += f"\n\nCODE (first 1000 chars):\n{code[:1000]}"
        
        prompt = f"""Analyze this student submission and classify it.

RUBRIC CONTEXT:
{rubric_summary}

{submission_section}

CLASSIFICATION TASK:
Determine the submission characteristics and potential issues.

Return ONLY valid JSON (no markdown, no extra text):
{{
    "content_type": "code|text_document|document_with_images|mixed",
    "domain": "computer_science|engineering|finance|medical|general",
    "complexity": "simple|moderate|complex",
    "confidence": 0.0_to_1.0,
    "issues": [
        {{"description": "issue text", "severity": "error|warning|info"}},
        ...
    ] or null
}}

Guidelines:
- content_type: Describe the primary form (code-heavy, text, mixed, etc.)
- domain: Infer from topic (CS for algorithms/data structures, Engineering for systems, etc.)
- complexity: Based on submission length, depth, technical detail
- confidence: How confident in this classification (0.7+ for good confidence)
- issues: Optional list of preliminary concerns (missing info, too brief, unclear, etc.)
"""
        return prompt
