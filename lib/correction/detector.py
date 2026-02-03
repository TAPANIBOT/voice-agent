import re
from typing import Dict, List

class AmbiguityDetector:
    """Detect ambiguous/unclear user responses"""
    
    def __init__(self):
        # Keywords indicating uncertainty
        self.uncertainty_keywords = [
            "ehkä", "kai", "luultavasti", "varmaan",
            "en tiedä", "en ole varma", "mites",
            "maybe", "probably", "not sure", "dunno"
        ]
        
        # Short responses (< 3 words often ambiguous)
        self.short_threshold = 3
    
    def detect(self, text: str, confidence: float = None) -> Dict:
        """
        Detect ambiguity in user input
        
        Returns:
            {
                "is_ambiguous": bool,
                "reason": str,
                "confidence_score": float
            }
        """
        text_lower = text.lower().strip()
        words = text_lower.split()
        
        # Check 1: Uncertainty keywords
        for keyword in self.uncertainty_keywords:
            if keyword in text_lower:
                return {
                    "is_ambiguous": True,
                    "reason": f"uncertainty_keyword: {keyword}",
                    "confidence_score": 0.4
                }
        
        # Check 2: Very short response
        if len(words) < self.short_threshold:
            return {
                "is_ambiguous": True,
                "reason": f"short_response: {len(words)} words",
                "confidence_score": 0.5
            }
        
        # Check 3: STT confidence (if provided)
        if confidence and confidence < 0.7:
            return {
                "is_ambiguous": True,
                "reason": f"low_stt_confidence: {confidence}",
                "confidence_score": confidence
            }
        
        # No ambiguity detected
        return {
            "is_ambiguous": False,
            "reason": "clear",
            "confidence_score": 1.0
        }