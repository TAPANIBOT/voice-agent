from typing import Dict

class ResponseAdapter:
    """Adapt response tone based on detected emotion"""
    
    def __init__(self):
        # Tone adjustments per emotion
        self.tone_profiles = {
            "positive": {
                "prefix": "",
                "pace": "normal",
                "stability": 0.5,  # ElevenLabs param
                "similarity_boost": 0.75
            },
            "negative": {
                "prefix": "",  # "Ymmärrän että olet turhautunut. "
                "pace": "slower",
                "stability": 0.7,  # More stable = calmer
                "similarity_boost": 0.5
            },
            "neutral": {
                "prefix": "",
                "pace": "normal",
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
    
    def adapt_text(self, text: str, emotion_info: Dict) -> str:
        """
        Add emotion-appropriate prefix/adjustments to text
        
        Args:
            text: original response
            emotion_info: from EmotionAnalyzer
        
        Returns:
            Adjusted text
        """
        emotion = emotion_info.get("primary_emotion", "neutral")
        profile = self.tone_profiles.get(emotion, self.tone_profiles["neutral"])
        
        # Add prefix if needed
        prefix = profile["prefix"]
        if prefix:
            text = prefix + text
        
        return text
    
    def get_tts_settings(self, emotion_info: Dict) -> Dict:
        """
        Get ElevenLabs voice settings based on emotion
        
        Returns:
            {
                "stability": float,
                "similarity_boost": float,
                "style": float (0-1, optional)
            }
        """
        emotion = emotion_info.get("primary_emotion", "neutral")
        profile = self.tone_profiles.get(emotion, self.tone_profiles["neutral"])
        
        return {
            "stability": profile["stability"],
            "similarity_boost": profile["similarity_boost"],
            "style": 0.0  # Reserved for future use
        }
    
    def should_slow_down(self, emotion_info: Dict) -> bool:
        """Check if response should be slower (negative emotion)"""
        emotion = emotion_info.get("primary_emotion", "neutral")
        return emotion == "negative"