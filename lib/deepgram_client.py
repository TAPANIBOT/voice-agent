import asyncio
import websockets
import json
import logging
from typing import AsyncIterator

class STTResult:
    def __init__(self, text: str, is_final: bool, confidence: float, timestamp: float):
        self.text = text
        self.is_final = is_final
        self.confidence = confidence
        self.timestamp = timestamp

class DeepgramSTT:
    def __init__(self, api_key: str, language: str = "fi", model: str = "nova-3"):
        self.api_key = api_key
        self.language = language
        self.model = model
        self.websocket = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.logger = logging.getLogger(__name__)

    async def start_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[STTResult]:
        """Start streaming audio to Deepgram and yield STT results."""
        url = f"wss://api.deepgram.com/v1/listen?model={self.model}&language={self.language}"
        
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.websocket = await websockets.connect(
                    url,
                    extra_headers={"Authorization": f"Token {self.api_key}"},
                    open_timeout=5,
                    ping_interval=20,
                    ping_timeout=60
                )
                self.reconnect_attempts = 0
                self.logger.info("WebSocket connection established")
                
                # Start streaming audio
                async for chunk in audio_stream:
                    await self.websocket.send(chunk)
                    
                    # Get response from Deepgram
                    response = await self.websocket.recv()
                    data = json.loads(response)
                    
                    if "channel_index" in data:
                        # Process interim/final results
                        for result in data.get("results", []):
                            is_final = result.get("is_final", False)
                            text = result.get("alternatives", [{}])[0].get("transcript", "")
                            confidence = result.get("alternatives", [{}])[0].get("confidence", 0.0)
                            timestamp = result.get("timestamp", 0.0)
                            
                            yield STTResult(
                                text=text,
                                is_final=is_final,
                                confidence=confidence,
                                timestamp=timestamp
                            )
                
            except (websockets.ConnectionClosed, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                self.logger.warning(f"Connection error: {e}. Reconnecting...")
                self.reconnect_attempts += 1
                await asyncio.sleep(2 ** self.reconnect_attempts)  # Exponential backoff
                continue
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                break
            finally:
                if self.websocket:
                    await self.websocket.close()
                    self.logger.info("WebSocket connection closed")

    async def stop_stream(self):
        """Stop the WebSocket connection gracefully."""
        if self.websocket:
            await self.websocket.close()
            self.logger.info("Stream stopped gracefully")

# Example usage (for testing purposes)
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def test_stream():
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            print("DEEPGRAM_API_KEY not found in environment variables")
            return
            
        # Create a simple audio stream for testing
        async def dummy_audio_stream():
            # In a real scenario, this would be your audio data
            yield b"dummy audio data"
            await asyncio.sleep(1)
            yield b"more dummy data"
        
        stt = DeepgramSTT(api_key)
        try:
            async for result in stt.start_stream(dummy_audio_stream()):
                print(f"Text: {result.text}, Final: {result.is_final}, Confidence: {result.confidence}")
        finally:
            await stt.stop_stream()
    
    asyncio.run(test_stream())