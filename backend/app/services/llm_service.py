from typing import Dict, Optional, Tuple
import httpx
import os
from dotenv import load_dotenv
import json

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


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
        Evaluate assignment using Groq LLM.
        
        Args:
            content: Assignment text content
            code: Code content if present
            rubric_criteria: List of evaluation criteria
            use_mock: If True, use mock evaluation
        
        Returns:
            Tuple of (scores, feedback, evidence, confidence)
            - scores: Dict[criterion_id -> score]
            - feedback: Dict[criterion_id -> feedback text]
            - evidence: Dict[criterion_id -> evidence excerpt]
            - confidence: Overall confidence score (0.0-1.0)
        """
        
        if use_mock:
            return LLMEvaluationService._mock_evaluate(content, code, rubric_criteria)
        
        # Call actual Groq API
        return await LLMEvaluationService._groq_evaluate(content, code, rubric_criteria)

    @staticmethod
    def _mock_evaluate(
        content: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """Mock evaluation for testing."""
        
        scores = {}
        feedback = {}
        evidence = {}
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("id")
            
            # Mock scoring logic
            if criterion_id == "clarity":
                score = 75.0 if len(content) > 100 else 50.0
                fb = "Good explanation with room for improvement in clarity."
            elif criterion_id == "completeness":
                score = 80.0
                fb = "Covers most required aspects."
            elif criterion_id == "code_quality":
                score = 70.0 if code and len(code) > 50 else 0.0
                fb = "Code structure is reasonable with some optimization opportunities."
            elif criterion_id == "correctness":
                score = 85.0
                fb = "Logic and implementation appear correct."
            elif criterion_id == "documentation":
                score = 60.0
                fb = "Documentation could be more detailed."
            elif criterion_id == "organization":
                score = 75.0
                fb = "Well-organized with logical flow."
            elif criterion_id == "originality":
                score = 70.0
                fb = "Shows independent thought with some unique insights."
            elif criterion_id == "overall":
                score = 75.0
                fb = "Solid submission overall."
            else:
                score = 70.0
                fb = f"Assessment for {criterion.get('name', 'Unknown')} criterion."
            
            scores[criterion_id] = score
            feedback[criterion_id] = fb
            evidence[criterion_id] = content[:200] if content else "No content"
        
        confidence = 0.82  # Mock confidence
        
        return scores, feedback, evidence, confidence

    @staticmethod
    async def _groq_evaluate(
        content: str,
        code: Optional[str],
        rubric_criteria: list
    ) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str], float]:
        """Evaluate using Groq API."""
        
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set. Using mock evaluation.")
        
        # Build prompt
        criteria_str = "\n".join([
            f"- {c.get('name')}: {c.get('description')} (max {c.get('max_points')} points)"
            for c in rubric_criteria
        ])
        
        prompt = f"""Evaluate the following assignment against these criteria:

{criteria_str}

ASSIGNMENT CONTENT:
{content}

{'CODE:' if code else ''}
{code if code else ''}

Provide your evaluation in JSON format with the following structure:
{{
    "scores": {{"criterion_id": score_0_to_100, ...}},
    "feedback": {{"criterion_id": "feedback text", ...}},
    "evidence": {{"criterion_id": "evidence excerpt", ...}},
    "confidence": 0.0_to_1.0
}}

Be precise and educational in your feedback."""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "mixtral-8x7b-32768",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 2048
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    response_content = result["choices"][0]["message"]["content"]
                    
                    # Parse JSON response
                    eval_data = json.loads(response_content)
                    return (
                        eval_data.get("scores", {}),
                        eval_data.get("feedback", {}),
                        eval_data.get("evidence", {}),
                        eval_data.get("confidence", 0.8)
                    )
                else:
                    raise ValueError(f"Groq API error: {response.status_code}")
        
        except Exception as e:
            print(f"Groq API error: {e}. Falling back to mock evaluation.")
            return LLMEvaluationService._mock_evaluate(content, code, rubric_criteria)
