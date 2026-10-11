"""
Grading Service - Stage 2 of two-stage evaluation pipeline.

Routes to appropriate grading model based on submission classification:
- Simple submissions → Fast model (gpt-oss-20b)
- Complex submissions → Reasoning model (gpt-oss-120b)
"""

import json
import httpx
import os
import asyncio
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
from app.services.groq_models import get_model, ModelCategory, select_grading_model
from app.services.rubric_engine import RubricEngine

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_REQUEST_TIMEOUT = 60


class GradingService:
    """Service for grading submissions in Stage 2 with intelligent model routing."""

    @staticmethod
    async def grade(
        text: str,
        code: Optional[str],
        rubric_criteria: list,
        classification: Dict[str, str],
        use_mock: bool = False
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float, str]:
        """
        Grade a submission using intelligent model routing based on classification.
        
        Args:
            text: Submission text content
            code: Code content if present
            rubric_criteria: List of evaluation criteria
            classification: Dict with content_type, domain, complexity
            use_mock: If True, use mock grading instead of real API
        
        Returns:
            Tuple of (scores, feedback, evidence, confidence, grading_model)
            - scores: Dict[criterion_id -> score] (clamped to [0, max_points])
            - feedback: Dict[criterion_id -> feedback text]
            - evidence: Dict[criterion_id -> evidence excerpt]
            - confidence: 0.0-1.0 grading confidence
            - grading_model: ID of model actually used for grading
        """
        
        if use_mock:
            return GradingService._mock_grade(text, code, rubric_criteria)
        
        # Select appropriate model based on classification
        selected_model = select_grading_model(classification)

        # Try real Groq grading with 2 attempts
        max_retries = 2
        for attempt in range(max_retries):
            try:
                scores, feedback, evidence, confidence = await GradingService._groq_grade(
                    text, code, rubric_criteria, selected_model
                )
                return scores, feedback, evidence, confidence, selected_model
            except ValueError as e:
                if attempt == max_retries - 1:
                    # Last attempt failed; fall back to mock
                    print(f"Grading failed after {max_retries} attempts: {e}")
                    print("Falling back to mock grading.")
                    scores, feedback, evidence, confidence, _ = GradingService._mock_grade(text, code, rubric_criteria)
                    return scores, feedback, evidence, confidence, selected_model
                else:
                    print(f"Grading attempt {attempt + 1} failed: {e}. Retrying...")
                    await asyncio.sleep(1)  # Brief delay before retry

        # Guard: should be unreachable with max_retries >= 1, but guarantees the declared
        # return type is always satisfied — prevents an implicit None if max_retries is
        # ever changed to 0 or the loop logic is refactored in the future.
        raise ValueError("GradingService.grade exhausted all retry attempts without returning.")

    @staticmethod
    async def _groq_grade(
        text: str,
        code: Optional[str],
        rubric_criteria: list,
        model: str
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """Grade using Groq API with response validation."""
        
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set")
        
        prompt = GradingService._build_grading_prompt(text, code, rubric_criteria)
        
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
            raise ValueError(f"Failed to parse grading JSON response: {e}")
        except httpx.TimeoutException:
            raise ValueError("Grading request timed out")
        except httpx.RequestError as e:
            raise ValueError(f"Grading request failed: {e}")

    @staticmethod
    def _mock_grade(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float, str]:
        """Mock grading for testing. Respects max_points for each criterion."""
        
        scores = {}
        feedback = {}
        evidence = {}
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("key", criterion.get("id", "unknown"))
            max_points = criterion.get("max_points", 100)
            
            # Generate mock score between 70-85% of max
            score = max_points * (0.7 + (len(criterion_id) % 15) / 100)
            
            # Clamp to valid range
            scores[criterion_id] = round(min(max_points, max(0, score)), 2)
            
            # Mock feedback
            criterion_name = criterion.get("label", criterion.get("name", criterion_id))
            feedback[criterion_id] = f"Good work on {criterion_name}. Shows understanding of the concepts."
            
            # Mock evidence
            evidence[criterion_id] = "Submission demonstrates understanding of the rubric criteria."
        
        confidence = 0.75  # Mock confidence
        
        return scores, feedback, evidence, confidence, "mock"

    @staticmethod
    def _build_grading_prompt(
        text: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> str:
        """Build prompt for grading stage with explicit per-criterion max_points."""
        
        # Build criteria descriptions with explicit score constraints
        criteria_str = "\n".join([
            f"- key `{c.get('key', c.get('id'))}`, label: {c.get('label', c.get('name'))}\n"
            f"  Description: {c.get('description')}\n"
            f"  SCORE THIS OUT OF EXACTLY {int(c.get('max_points', 100))} POINTS"
            for c in rubric_criteria
        ])
        
        # Build submission content section
        submission_section = f"ASSIGNMENT TEXT:\n{text}"
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
