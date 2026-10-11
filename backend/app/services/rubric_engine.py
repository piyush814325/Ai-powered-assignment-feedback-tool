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
        Clamps each criterion score to [0, max_points] to prevent out-of-range values.
        
        Args:
            content: Extracted text content
            code: Extracted code (if any)
            rubric_criteria: List of rubric criteria with max_points and weight
            scores: Dict of criterion_id -> score
            feedback: Dict of criterion_id -> feedback text
            evidence: Dict of criterion_id -> evidence excerpt
        
        Returns:
            Tuple of (total_score, avg_confidence)
            
        Note:
            If a score is out of range (e.g., model returned 75 for a 15-point criterion),
            it is clamped to [0, max_points]. This should be accompanied by a server-side
            warning/retry in the caller; clamping alone hides the real bug that the model
            didn't receive/follow the max_points constraint.
        """
        total_score = 0.0
        clamped_count = 0
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("key", criterion.get("id"))
            max_points = float(criterion.get("max_points", 0))
            
            if criterion_id in scores:
                score = float(scores[criterion_id])
                # Clamp to valid range
                clamped_score = max(0.0, min(score, max_points))
                
                if clamped_score != score:
                    clamped_count += 1
                    print(f"WARNING: Score for '{criterion_id}' was {score}, clamped to {clamped_score} (max {max_points})")
                
                total_score += clamped_score

        # Average confidence (mock: 0.85 baseline, will be replaced by LLM confidence)
        avg_confidence = 0.85
        
        if clamped_count > 0:
            print(f"WARNING: {clamped_count} out of {len(rubric_criteria)} criterion scores were out of range and clamped.")
        
        return round(total_score, 2), avg_confidence

    @staticmethod
    def validate_scores(scores: Dict[str, float], rubric_criteria: list) -> Tuple[bool, str]:
        """
        Validate that all scores are within acceptable ranges.
        
        Args:
            scores: Dict of criterion_id -> score
            rubric_criteria: List of rubric criteria
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        for criterion in rubric_criteria:
            criterion_id = criterion.get("key", criterion.get("id"))
            max_points = float(criterion.get("max_points", 0))
            
            if criterion_id not in scores:
                return False, f"Missing score for criterion '{criterion_id}'"
            
            score = scores[criterion_id]
            if not isinstance(score, (int, float)):
                return False, f"Score for '{criterion_id}' is not numeric: {score}"
            
            # Allow a small tolerance for floating point errors (e.g., 100.001 for a 100-point criterion)
            tolerance = 0.01
            if score < -tolerance or score > max_points + tolerance:
                return False, f"Score for '{criterion_id}' is {score}, outside range [0, {max_points}]"
        
        return True, ""

    @staticmethod
    def get_score_breakdown(
        scores: Dict[str, float],
        rubric_criteria: list
    ) -> Dict[str, any]:
        """Get detailed score breakdown per criterion."""
        breakdown = {}
        
        for criterion in rubric_criteria:
            criterion_id = criterion.get("key", criterion.get("id"))
            if criterion_id in scores:
                max_pts = criterion.get("max_points", 100)
                score = scores[criterion_id]
                # Clamp for display
                clamped_score = max(0.0, min(score, max_pts))
                breakdown[criterion_id] = {
                    "name": criterion.get("name"),
                    "score": clamped_score,
                    "max_points": max_pts,
                    "percentage": (clamped_score / max_pts) * 100 if max_pts else 0
                }
        
        return breakdown

