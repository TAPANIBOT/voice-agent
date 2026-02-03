import os
from typing import Dict, Optional
from deepgram import DeepgramClient, PrerecordedOptions

class EmotionAnalyzer:
    """Analyze emotion from audio + text"""
    
    def __init__(self):
        self.deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        
        # Simple sentiment keywords (Finnish)
        self.positive_words = ["hyvä", "kiitos", "loistava", "mahtava", "ok", "joo"]
        self.negative_words = ["huono", "ei", "paha", "ikävä", "vittu", "saatana"]
        self.neutral_words = ["ehkä", "kai", "hmm"]
    
    async def analyze_audio(self, audio_url: str) -> Dict:
        """
        Analyze emotion from audio using Deepgram
        
        Returns:
            {
                "primary_emotion": str,
                "confidence": float,
                "all_emotions": Dict[str, float]
            }
        """
        try:
            options = PrerecordedOptions(
                model="nova-2",
                language="fi",
                sentiment=True,
                detect_topics=False
            )
            
            response = await self.deepgram.listen.prerecorded.v("1").transcribe_url(
                {"url": audio_url}, options
            )
            
            # Extract sentiment
            sentiment = response.results.channels[0].alternatives[0].sentiment
            
            return {
                "primary_emotion": sentiment,
                "confidence": 0.8,  # Deepgram doesn't provide confidence for sentiment
                "all_emotions": {sentiment: 0.8}
            }
        
        except Exception as e:
            return {
                "primary_emotion": "neutral",
                "confidence": 0.5,
                "all_emotions": {"neutral": 0.5},
                "error": str(e)
            }
    
    def analyze_text(self, text: str) -> Dict:
        """
        Simple keyword-based sentiment analysis
        
        Returns same format as analyze_audio
        """
        text_lower = text.lower()
        
        positive_count = sum(1 for word in self.positive_words if word in text_lower)
        negative_count = sum(1 for word in self.negative_words if word in text_lower)
        
        if positive_count > negative_count:
            emotion = "positive"
            confidence = min(0.6 + (positive_count * 0.1), 0.9)
        elif negative_count > positive_count:
            emotion = "negative"
            confidence = min(0.6 + (negative_count * 0.1), 0.9)
        else:
            emotion = "neutral"
            confidence = 0.5
        
        return {
            "primary_emotion": emotion,
            "confidence": confidence,
            "all_emotions": {emotion: confidence}
        }