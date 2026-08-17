from typing import Dict, Optional, Tuple
import json
from datetime import datetime


class RubricEngine:
    """Scores submissions against a rubric with weighted criteria."""

    @staticmethod
    def evaluate(
        content: str,
        code: Optional[str],
        rubric_criteria: list,
        scores: Dict[str, float],
        feedback: Dict[str, str],
        evidence: Dict[str, str]
    ) -> Tuple[float, float]:
        """
        Calculate total score and average confidence.
        
        Args:
            content: Extracted text content
            code: Extracted code (if any)
            rubric_criteria: List of rubric criteria with max_points and weight
            scores: Dict of criterion_id -> score
            feedback: Dict of criterion_id -> feedback text
            evidence: Dict of criterion_id -> evidence excerpt
        
        Returns:
            Tuple of (total_score, avg_confidence)
        """
        total_score = 0.0
        total_weight = 0.0
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("id")
            max_points = criterion.get("max_points", 0)
            weight = criterion.get("weight", 1.0)
            
            if criterion_id in scores:
                score = scores[criterion_id]
                # Normalize to criterion max_points
                weighted_score = (score / 100) * max_points * weight
                total_score += weighted_score
                total_weight += weight
        
        # Average confidence (mock: 0.85 baseline, will be replaced by LLM confidence)
        avg_confidence = 0.85
        
        return total_score, avg_confidence

    @staticmethod
    def get_score_breakdown(
        scores: Dict[str, float],
        rubric_criteria: list
    ) -> Dict[str, any]:
        """Get detailed score breakdown per criterion."""
        breakdown = {}
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("id")
            if criterion_id in scores:
                max_pts = criterion.get("max_points", 100)
                breakdown[criterion_id] = {
                    "name": criterion.get("name"),
                    "score": scores[criterion_id],
                    "max_points": max_pts,
                    "percentage": (scores[criterion_id] / max_pts) * 100 if max_pts else 0
                }
        
        return breakdown
