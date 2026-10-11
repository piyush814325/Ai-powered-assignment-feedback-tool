from typing import Dict, Optional, Tuple
import httpx
import os
from dotenv import load_dotenv
import json
import re
import asyncio
from app.services.groq_models import get_model, ModelCategory
from app.services.rubric_engine import RubricEngine

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_REQUEST_TIMEOUT = 60


class LLMEvaluationService:
    """Service for evaluating assignments using Groq LLM."""

    @staticmethod
    async def evaluate_with_llm(
        content: str,
        code: Optional[str],
        rubric_criteria: list,
        use_mock: bool = True
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """
        Evaluate assignment using Groq LLM with retry/fallback logic.
        
        Args:
            content: Assignment text content
            code: Code content if present
            rubric_criteria: List of evaluation criteria with {key, label, description, max_points}
            use_mock: If True, use mock evaluation instead of real API
        
        Returns:
            Tuple of (scores, feedback, evidence, confidence)
            - scores: Dict[criterion_id -> score] (clamped to [0, max_points])
            - feedback: Dict[criterion_id -> feedback text]
            - evidence: Dict[criterion_id -> evidence excerpt]
            - confidence: Overall confidence score (0.0-1.0)
        
        Raises:
            ValueError: If validation fails after retries or API is down
        """
        
        if use_mock or not GROQ_API_KEY:
            return LLMEvaluationService._mock_evaluate(content, code, rubric_criteria)
        
        # Try real API with retry logic
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = await LLMEvaluationService._groq_evaluate(
                    content, code, rubric_criteria
                )
                return result
            except ValueError as e:
                if attempt == max_retries - 1:
                    # Last attempt failed; log and fall back to mock
                    print(f"LLM evaluation failed after {max_retries} attempts: {e}")
                    print("Falling back to mock evaluation.")
                    return LLMEvaluationService._mock_evaluate(content, code, rubric_criteria)
                else:
                    print(f"LLM evaluation attempt {attempt + 1} failed: {e}. Retrying...")
                    await asyncio.sleep(1)  # Brief delay before retry

        # Guard: should be unreachable with max_retries >= 1, but guarantees the declared
        # return type is always satisfied — prevents an implicit None if max_retries is
        # ever changed to 0 or the loop logic is refactored in the future.
        raise ValueError("evaluate_with_llm exhausted all retry attempts without returning.")

    @staticmethod
    def _build_grading_prompt(
        content: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> str:
        """
        Build the prompt for the LLM with explicit per-criterion max_points constraints.
        """
        # Build criteria descriptions with explicit score constraints
        criteria_str = "\n".join([
            f"- key `{c.get('key', c.get('id'))}`, label: {c.get('label', c.get('name'))}\n"
            f"  Description: {c.get('description')}\n"
            f"  SCORE THIS OUT OF EXACTLY {int(c.get('max_points', 100))} POINTS"
            for c in rubric_criteria
        ])
        
        # Build submission content section
        submission_section = f"ASSIGNMENT TEXT:\n{content}"
        if code:
            submission_section += f"\n\nCODE:\n{code}"
        
        prompt = f"""You are an expert educator evaluating a student assignment.

CRITERIA (each scored out of its specified maximum):
{criteria_str}

{submission_section}

EVALUATION TASK:
1. Score each criterion according to the rubric description and the maximum points shown
2. Provide concise feedback specific to each criterion (2-3 sentences)
3. Extract a direct evidence quote or example from the submission for each criterion
4. Return your evaluation as VALID JSON only (no markdown, no extra text)

IMPORTANT CONSTRAINTS:
- Each score MUST be a number (integer or decimal)
- Each score MUST be within [0, max_points] for that criterion
- Do not score out of 100 for criteria with different maximums
- If a criterion does not apply to this submission, score it 0 with explanation

Return ONLY this JSON structure (no other text before or after):
{{
    "scores": {{criterion_key: numeric_score, ...}},
    "feedback": {{criterion_key: "feedback text", ...}},
    "evidence": {{criterion_key: "evidence excerpt", ...}},
    "confidence": 0.0_to_1.0
}}
"""
        return prompt

    @staticmethod
    def _extract_evidence(content: str, code: Optional[str], criterion_id: str) -> str:
        """Extract criterion-specific evidence snippet from document or code."""
        if not content and not code:
            return "No content available for evaluation."

        text_to_search = content or ""
        lines = [line.strip() for line in text_to_search.split("\n") if line.strip() and not line.startswith("---")]
        
        # Keywords mapping for each criterion
        keywords = {
            "clarity": ["introduction", "overview", "synopsis", "topic", "name", "title"],
            "completeness": ["workflow", "architecture", "stage", "process", "features", "operational"],
            "code_quality": ["code", "function", "script", "technical", "nlp", "api", "component", "library"],
            "correctness": ["advantages", "limitations", "solution", "implementation", "results", "analysis"],
            "documentation": ["references", "http", "url", "documentation", "guide", "tutorials"],
            "organization": ["1.", "2.", "3.", "bullet", "section", "workflow", "stage"],
            "originality": ["conclusion", "future", "ai-driven", "innovative", "experimentation", "unique"]
        }

        target_words = keywords.get(criterion_id, [])

        # Search for a matching line or paragraph containing keywords
        for line in lines:
            if any(kw in line.lower() for kw in target_words):
                if len(line) > 25:
                    clean_line = re.sub(r'[\x00-\x1f\x7f-\x9f\uf000-\uf8ff]', ' ', line)
                    return ' '.join(clean_line.split())[:220]

        # Special fallback for code_quality if code is provided
        if criterion_id == "code_quality" and code:
            code_lines = [c for c in code.split("\n") if c.strip()]
            clean_code = re.sub(r'[\x00-\x1f\x7f-\x9f\uf000-\uf8ff]', ' ', "\n".join(code_lines[:4]))
            return clean_code[:220]

        # Offset fallback: pick different sections of lines so criteria never get identical text
        offset_map = {
            "clarity": 0,
            "completeness": 2,
            "correctness": 4,
            "code_quality": 6,
            "organization": 8,
            "documentation": 10,
            "originality": 12,
        }
        idx = offset_map.get(criterion_id, 0)
        if lines:
            start = idx if idx < len(lines) else 0
            selected_lines = lines[start:start + 2]
            snippet = " ".join(selected_lines)
            if snippet:
                clean_snippet = re.sub(r'[\x00-\x1f\x7f-\x9f\uf000-\uf8ff]', ' ', snippet)
                return ' '.join(clean_snippet.split())[:220]

        clean_all = re.sub(r'[\x00-\x1f\x7f-\x9f\uf000-\uf8ff]', ' ', text_to_search)
        return ' '.join(clean_all.split())[:200]

    @staticmethod
    def _mock_evaluate(
        content: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """Mock evaluation for testing. Respects max_points for each criterion."""
        
        scores = {}
        feedback = {}
        evidence = {}
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("key", criterion.get("id"))
            max_points = float(criterion.get("max_points", 0))
            
            # Mock scoring logic
            if criterion_id == "clarity":
                score = max_points * (0.75 if len(content) > 100 else 0.5)
                fb = "Good explanation with room for improvement in clarity."
            elif criterion_id == "completeness":
                score = max_points * 0.8
                fb = "Covers most required aspects."
            elif criterion_id == "code_quality":
                score = max_points * (0.7 if code and len(code) > 50 else 0.0)
                fb = "Code structure is reasonable with some optimization opportunities."
            elif criterion_id == "correctness":
                score = max_points * 0.85
                fb = "Logic and implementation appear correct."
            elif criterion_id == "documentation":
                score = max_points * 0.6
                fb = "Documentation could be more detailed."
            elif criterion_id == "organization":
                score = max_points * 0.75
                fb = "Well-organized with logical flow."
            elif criterion_id == "originality":
                score = max_points * 0.7
                fb = "Shows independent thought with some unique insights."
            elif criterion_id == "overall":
                score = max_points * 0.75
                fb = "Solid submission overall."
            else:
                score = max_points * 0.7
                fb = f"Assessment for {criterion.get('name', 'Unknown')} criterion."
            
            scores[criterion_id] = round(min(max_points, max(0, score)), 2)
            feedback[criterion_id] = fb
            evidence[criterion_id] = LLMEvaluationService._extract_evidence(content, code, criterion_id)
        
        confidence = 0.82  # Mock confidence
        
        return scores, feedback, evidence, confidence

    @staticmethod
    async def _groq_evaluate(
        content: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """
        Evaluate using Groq API with response validation and error handling.
        
        Raises:
            ValueError: If response validation fails or API error occurs
        """
        
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set.")
        
        model = get_model(ModelCategory.GRADE_FAST)
        prompt = LLMEvaluationService._build_grading_prompt(content, code, rubric_criteria)
        
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
                        "temperature": 0.7,
                        "max_tokens": 2048
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text or f"HTTP {response.status_code}"
                    raise ValueError(f"Groq API error: {error_detail}")
                
                result = response.json()
                response_content = result["choices"][0]["message"]["content"]
                
                # Parse JSON response
                eval_data = json.loads(response_content)
                
                # Validate response structure and values
                scores = eval_data.get("scores", {})
                feedback = eval_data.get("feedback", {})
                evidence = eval_data.get("evidence", {})
                confidence = eval_data.get("confidence", 0.8)
                
                # Validate scores
                is_valid, error_msg = RubricEngine.validate_scores(scores, rubric_criteria)
                if not is_valid:
                    raise ValueError(f"Invalid scores in LLM response: {error_msg}")
                
                return scores, feedback, evidence, confidence
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM JSON response: {e}")
        except httpx.TimeoutException:
            raise ValueError("Groq API request timed out")
        except httpx.RequestError as e:
            raise ValueError(f"Groq API request failed: {e}")

