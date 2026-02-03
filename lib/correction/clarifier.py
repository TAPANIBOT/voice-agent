from typing import Dict, Optional
import random

class Clarifier:
    """Generate clarification responses"""
    
    def __init__(self, language: str = "fi"):
        self.language = language
        self.templates = {
            "fi": [
                "Anteeksi, en ole varma ymmärsinkö oikein. Tarkoititko {options}?",
                "Voisitko toistaa? En aivan saanut selvää.",
                "Hmm, kuulin vain '{heard}'. Voisitko sanoa uudelleen?",
                "Pahoittelut, yhteys pätkii hieman. Mitä sanoit?"
            ],
            "en": [
                "Sorry, I'm not sure I understood. Did you mean {options}?",
                "Could you repeat that? I didn't quite catch it.",
                "Hmm, I only heard '{heard}'. Could you say that again?",
                "Apologies, the connection is a bit choppy. What did you say?"
            ]
        }
    
    def generate(self, ambiguity_info: Dict, user_text: str, options: list[str] = None) -> str:
        """
        Generate clarification response
        
        Args:
            ambiguity_info: from AmbiguityDetector.detect()
            user_text: what user said
            options: possible interpretations (optional)
        
        Returns:
            Clarification prompt in target language
        """
        templates = self.templates.get(self.language, self.templates["en"])
        reason = ambiguity_info.get("reason", "")
        
        # Select appropriate template
        if "uncertainty_keyword" in reason and options:
            # Offer options
            template = templates[0]
            options_str = " vai ".join(options) if self.language == "fi" else " or ".join(options)
            return template.format(options=options_str)
        
        elif "low_stt_confidence" in reason or "short_response" in reason:
            # Ask to repeat
            template = random.choice(templates[1:3])
            return template.format(heard=user_text[:30])
        
        else:
            # Generic clarification
            return random.choice(templates)