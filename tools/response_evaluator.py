"""
Response quality evaluation - detect hallucinations, errors, and weak outputs.
Provides feedback to improve model responses.
"""

import re
from typing import Dict, List, Tuple
from enum import Enum


class ResponseQuality(Enum):
    """Quality assessment of a model response."""
    EXCELLENT = "excellent"    # Direct answer, confident, well-structured
    GOOD = "good"             # Useful, mostly correct
    ACCEPTABLE = "acceptable" # Answers the question but has issues
    WEAK = "weak"             # Missing context or wrong direction
    ERROR = "error"           # Incorrect, hallucinated, or harmful


class ResponseEvaluator:
    """Evaluate response quality and detect issues."""
    
    # Patterns that suggest hallucination or weak responses
    HALLUCINATION_INDICATORS = [
        r"i (don't|cannot|don't have|lack|can't provide) (access|info|knowledge|details)",
        r"(as of my last|according to my training|in my training data)",
        r"(i'm not able|i'm unable|i'm not authorized) to",
        r"(that's (.{1,30})? responsibility|it's not my role|i'm not responsible)",
        r"^(i don't know|i'm unsure|i'm not sure|i don't have|i can't determine)",
    ]
    
    # Patterns that suggest good responses
    QUALITY_INDICATORS = [
        r"(specifically|concretely|here are|here's|the steps are|the steps:|step 1)",
        r"(because|due to|since|as a result|this means)",
        r"(for example|for instance|such as|like|e\.g\.)",
        r"(however|but|on the other hand|alternatively)",
    ]
    
    # Safety and accuracy issues
    RISKY_PATTERNS = [
        r"^(delete|rm|format|wipe|shutdown|reboot)",
        r"(without (backup|confirmation|asking)|force delete|force kill)",
        r"(run this|execute this|paste this) .{0,30}(no.*review|immediately)",
    ]
    
    # Common hallucination phrases
    HALLUCINATION_PHRASES = [
        "i will check the system",
        "from what i can tell",
        "based on my analysis",
        "in your system",
        "your personal",
        "your specific",
        "that would require",
    ]
    
    @classmethod
    def evaluate(cls, response: str, user_request: str = "") -> Dict[str, any]:
        """
        Evaluate response quality.
        
        Returns dict with:
            - quality: ResponseQuality enum
            - score: float 0-1
            - issues: list of detected problems
            - warnings: list of warnings
            - suggestions: list of improvement suggestions
        """
        if not response:
            return {
                "quality": ResponseQuality.WEAK,
                "score": 0.0,
                "issues": ["Empty response"],
                "warnings": [],
                "suggestions": ["Provide an actual answer"],
            }
        
        text = response.strip()
        
        # Check for hallucinations
        hallucination_score = cls._check_hallucinations(text)
        
        # Check for quality indicators
        quality_score = cls._check_quality(text)
        
        # Check length appropriateness
        length_score = cls._check_length(text, user_request)
        
        # Check for risky content
        risk_level = cls._check_safety(text)
        
        # Detect specific issues
        issues = []
        warnings = []
        suggestions = []
        
        if hallucination_score > 0.5:
            issues.append("Response may contain hallucinations or made-up details")
            suggestions.append("State assumptions explicitly: 'I'm assuming...'")
        
        if quality_score < 0.4:
            issues.append("Response lacks concrete details or examples")
            suggestions.append("Include specific steps, commands, or examples")
        
        if length_score < 0.3:
            issues.append("Response is too short to be useful")
            suggestions.append("Expand with more context or detail")
        elif length_score < 0.5:
            warnings.append("Response could be more detailed")
        
        if risk_level == "high":
            warnings.append("⚠️  Response contains potentially dangerous commands")
            suggestions.append("Add explicit warnings before risky operations")
        
        # Calculate overall score
        overall_score = (
            (1 - hallucination_score) * 0.4 +
            quality_score * 0.4 +
            length_score * 0.2
        )
        
        # Determine quality level
        if overall_score >= 0.85:
            quality = ResponseQuality.EXCELLENT
        elif overall_score >= 0.7:
            quality = ResponseQuality.GOOD
        elif overall_score >= 0.5:
            quality = ResponseQuality.ACCEPTABLE
        elif overall_score >= 0.3:
            quality = ResponseQuality.WEAK
        else:
            quality = ResponseQuality.ERROR
        
        return {
            "quality": quality,
            "quality_name": quality.value,
            "score": round(overall_score, 2),
            "scores": {
                "hallucination_risk": round(hallucination_score, 2),
                "quality_indicators": round(quality_score, 2),
                "length_appropriateness": round(length_score, 2),
            },
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "risk_level": risk_level,
        }
    
    @classmethod
    def _check_hallucinations(cls, text: str) -> float:
        """Return hallucination risk score (0-1)."""
        score = 0.0
        
        # Check for hallucination indicators
        indicators = sum(1 for p in cls.HALLUCINATION_INDICATORS 
                        if re.search(p, text, re.IGNORECASE))
        score += min(indicators * 0.2, 0.5)
        
        # Check for hallucination phrases
        phrases = sum(1 for p in cls.HALLUCINATION_PHRASES 
                     if p.lower() in text.lower())
        score += min(phrases * 0.15, 0.3)
        
        # Check if response admits uncertainty correctly
        admits_uncertainty = any(
            phrase in text.lower() 
            for phrase in ["i don't know", "i can't", "i'm not sure", "need more info"]
        )
        if admits_uncertainty:
            score -= 0.2  # This is actually good
        
        return min(score, 1.0)
    
    @classmethod
    def _check_quality(cls, text: str) -> float:
        """Return quality score (0-1)."""
        score = 0.0
        
        # Check for quality indicators
        indicators = sum(1 for p in cls.QUALITY_INDICATORS 
                        if re.search(p, text, re.IGNORECASE))
        score += min(indicators * 0.15, 0.6)
        
        # Check for structure (lists, steps, etc.)
        has_structure = any(
            marker in text 
            for marker in ["1.", "2.", "3.", "-", "•", "**", "##"]
        )
        if has_structure:
            score += 0.2
        
        # Check for executable content (code, commands)
        has_code = bool(re.search(r"```|`[^`]+`|python|bash|powershell", text))
        if has_code:
            score += 0.1
        
        return min(score, 1.0)
    
    @classmethod
    def _check_length(cls, text: str, request: str = "") -> float:
        """Check if response length is appropriate."""
        text_len = len(text)
        
        # Rough heuristics
        if text_len < 20:
            return 0.2  # Too short
        elif text_len < 50:
            return 0.4
        elif text_len < 500:
            return 0.8  # Good range
        elif text_len < 2000:
            return 0.7  # Slightly long but ok
        else:
            return 0.5  # Very long
    
    @classmethod
    def _check_safety(cls, text: str) -> str:
        """Assess safety level of response."""
        risky_count = sum(1 for p in cls.RISKY_PATTERNS 
                         if re.search(p, text, re.IGNORECASE | re.MULTILINE))
        
        if risky_count >= 2:
            return "high"
        elif risky_count >= 1:
            return "medium"
        else:
            return "low"
    
    @classmethod
    def get_improvement_prompt(cls, evaluation: Dict) -> str:
        """Generate a prompt for improving the response."""
        if evaluation["quality"] == ResponseQuality.EXCELLENT:
            return ""
        
        parts = ["The previous response could be improved:"]
        
        for issue in evaluation["issues"]:
            parts.append(f"- {issue}")
        
        if evaluation["suggestions"]:
            parts.append("\nSuggested improvements:")
            for suggestion in evaluation["suggestions"]:
                parts.append(f"- {suggestion}")
        
        return "\n".join(parts)
