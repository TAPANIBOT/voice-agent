from typing import List, Optional
import time


class Turn:
    def __init__(self, speaker: str, text: str, confidence: float):
        self.speaker = speaker
        self.text = text
        self.timestamp = time.time()
        self.confidence = confidence
        self.intent = self.detect_intent(text)
        self.sentiment = self.analyze_sentiment(text)

    @staticmethod
    def detect_intent(text: str) -> str:
        # Simple intent detection based on keywords
        text_lower = text.lower()
        if "how" in text_lower or "what" in text_lower or "why" in text_lower:
            return "question"
        elif "do" in text_lower or "make" in text_lower or "create" in text_lower:
            return "command"
        elif "hello" in text_lower or "hi" in text_lower:
            return "greeting"
        elif "bye" in text_lower or "goodbye" in text_lower:
            return "farewell"
        else:
            return "statement"

    @staticmethod
    def analyze_sentiment(text: str) -> str:
        # Simple sentiment analysis based on keywords
        positive_words = ["good", "great", "excellent", "happy", "thank"]
        negative_words = ["bad", "terrible", "awful", "sad", "angry", "frustrated"]
        
        text_lower = text.lower()
        if any(word in text_lower for word in positive_words):
            return "positive"
        elif any(word in text_lower for word in negative_words):
            return "negative"
        else:
            return "neutral"


class ConversationContext:
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.turns = []  # type: List[Turn]
        self.current_topic = None  # type: Optional[str]
        self.user_sentiment = "neutral"
        self.user_intent = "statement"
        self.metadata = {
            "call_duration": 0,
            "turn_count": 0,
            "last_update": time.time()
        }

    def add_turn(self, speaker: str, text: str, confidence: float):
        """Add a new turn to the conversation and update context."""
        new_turn = Turn(speaker, text, confidence)
        self.turns.append(new_turn)
        
        # Keep only last 10 turns
        if len(self.turns) > 10:
            self.turns = self.turns[-10:]
        
        # Update metadata
        self.metadata["turn_count"] = len(self.turns)
        self.metadata["call_duration"] = time.time() - self.turns[0].timestamp
        self.metadata["last_update"] = time.time()
        
        # Update current topic if user is speaking
        if speaker == "user":
            self.current_topic = self.extract_topic(text)
            
        # Update overall sentiment and intent based on user turns
        user_turns = [turn for turn in self.turns if turn.speaker == "user"]
        if user_turns:
            self.user_sentiment = max(
                (turn.sentiment, user_turns.count(turn.sentiment))
                for turn in user_turns
            )[0]
            self.user_intent = max(
                (turn.intent, user_turns.count(turn.intent))
                for turn in user_turns
            )[0]

    @staticmethod
    def extract_topic(text: str) -> Optional[str]:
        """Extract topic from text using simple keyword matching."""
        topic_keywords = {
            "weather": ["weather", "forecast", "temperature", "rain", "snow"],
            "time": ["time", "date", "day", "hour", "minute"],
            "news": ["news", "headlines", "events", "happening"],
            "help": ["help", "assistance", "support", "problem"],
            "general": ["hello", "hi", "bye", "goodbye", "thank"]
        }
        
        text_lower = text.lower()
        for topic, keywords in topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return topic
        return None

    def should_inject_filler(self) -> bool:
        """Determine if a filler response should be injected based on conversation complexity."""
        # Complexity factors: number of turns, sentiment changes, topic changes
        if len(self.turns) < 3:
            return False
        
        sentiment_changes = len(set(turn.sentiment for turn in self.turns))
        topic_changes = len(set(turn.intent for turn in self.turns if turn.speaker == "user"))
        
        return (sentiment_changes > 1 or topic_changes > 1) and self.metadata["turn_count"] % 3 == 0


# Example usage:
if __name__ == "__main__":
    # Create a new conversation context
    context = ConversationContext(call_id="test_call_123")
    
    # Add turns to the conversation
    context.add_turn("user", "Hello, how are you?", 0.95)
    context.add_turn("agent", "I'm good, thank you! How can I help you today?", 0.98)
    context.add_turn("user", "I need help with the weather forecast", 0.92)
    context.add_turn("agent", "Sure, which city are you interested in?", 0.95)
    context.add_turn("user", "I'm frustrated with this weather", 0.88)
    
    # Print conversation state
    print("Conversation Context:")
    print(f"Call ID: {context.call_id}")
    print(f"Current Topic: {context.current_topic}")
    print(f"User Sentiment: {context.user_sentiment}")
    print(f"User Intent: {context.user_intent}")
    print(f"Turn Count: {context.metadata['turn_count']}")
    print(f"Call Duration: {context.metadata['call_duration']:.2f} seconds")
    print("\nTurns:")
    for i, turn in enumerate(context.turns, 1):
        print(f"{i}. {turn.speaker}: {turn.text} (Intent: {turn.intent}, Sentiment: {turn.sentiment}, Confidence: {turn.confidence:.2f})")
    
    # Check if filler should be injected
    print(f"\nShould inject filler: {context.should_inject_filler()}")