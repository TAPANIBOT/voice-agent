"""
Human-like behavior logic for voice interactions.
"""
import random
from typing import Optional, List


def should_respond(audio_silence_ms: int, has_punctuation: bool, is_question: bool) -> bool:
    """
    Determines when the agent should respond based on turn-taking rules.
    
    Args:
        audio_silence_ms: Duration of silence in milliseconds
        has_punctuation: Whether the last text had punctuation
        is_question: Whether the last text was a question
        
    Returns:
        bool: True if agent should respond, False otherwise
    """
    # 0.3s wait after user stops
    if audio_silence_ms < 300:
        return False
    
    # 1.2s if no punctuation
    if not has_punctuation and audio_silence_ms < 1200:
        return False
    
    # Immediate if question
    if is_question and audio_silence_ms > 500:
        return True
    
    return True


def get_filler_word(complexity_score: int) -> Optional[str]:
    """
    Gets a Finnish filler word based on response complexity.
    
    Args:
        complexity_score: Score indicating response complexity (0-100)
        
    Returns:
        Optional[str]: Filler word or None if not needed
    """
    # 10% probability for complex responses
    if complexity_score > 50 and random.random() < 0.1:
        return random.choice(["hmm", "öö", "no siis", "joo"])
    return None


def calculate_pause_duration(context: str, importance: float) -> float:
    """
    Calculates natural pause duration before speaking.
    
    Args:
        context: Current conversation context
        importance: Importance of the response (0.0-1.0)
        
    Returns:
        float: Pause duration in seconds
    """
    base_pause = 0.3  # Minimum pause
    
    # Adjust for importance
    if importance > 0.7:
        base_pause += 0.2
    elif importance < 0.3:
        base_pause += 0.1
    
    # Adjust for context length
    word_count = len(context.split())
    if word_count > 50:
        base_pause += 0.1
    
    return max(0.2, base_pause)  # Minimum 200ms pause


def detect_barge_in(audio_volume_history: List[float]) -> bool:
    """
    Detects if user is trying to interrupt (barge-in).
    
    Args:
        audio_volume_history: List of recent audio volume samples
        
    Returns:
        bool: True if barge-in detected, False otherwise
    """
    if len(audio_volume_history) < 5:
        return False
    
    # Check if volume suddenly increases
    current_volume = audio_volume_history[-1]
    recent_volumes = audio_volume_history[-5:-1]
    
    if current_volume > max(recent_volumes) * 1.5:
        return True
    
    return False