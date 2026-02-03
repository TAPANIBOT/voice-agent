import os
import time
import aiohttp
import asyncio
from typing import AsyncIterator, Optional

class TTSChunk:
    def __init__(self, audio: bytes, duration_ms: float, timestamp: float):
        self.audio = audio
        self.duration_ms = duration_ms
        self.timestamp = timestamp

class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_flash_v2_5"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.base_url = "https://api.elevenlabs.io/v1/tts/stream"
        self.latency_data = []

    async def synthesize_stream(self, text: str, emotion: Optional[str] = None) -> AsyncIterator[TTSChunk]:
        """
        Stream TTS audio chunk by chunk from ElevenLabs API.
        
        Args:
            text: Text to synthesize
            emotion: Optional emotion tag (questioning, excited, thoughtful, concerned)
            
        Yields:
            TTSChunk objects containing audio data and metadata
        """
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/x-mulaw; rate=8000"
        }
        
        payload = {
            "text": text,
            "voice_id": self.voice_id,
            "model_id": self.model
        }
        
        if emotion:
            payload["emotion"] = emotion

        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        raise Exception(f"API Error: {response.status} - {await response.text()}")
                    
                    chunk_size = 160  # 20ms chunks for 8kHz μ-law
                    buffer = b""
                    chunk_timestamp = 0.0
                    
                    async for chunk in response.content.iter_chunked(chunk_size):
                        if chunk:
                            buffer += chunk
                            chunk_duration = len(chunk) / 160 * 20  # Convert bytes to ms
                            chunk_timestamp += chunk_duration / 1000  # Convert to seconds
                            
                            # Yield TTSChunk with audio data
                            yield TTSChunk(
                                audio=chunk,
                                duration_ms=chunk_duration,
                                timestamp=chunk_timestamp
                            )
        except Exception as e:
            print(f"Error in TTS streaming: {str(e)}")
            raise
        finally:
            latency = (time.time() - start_time) * 1000
            self.latency_data.append(latency)

    def get_latency_ms(self) -> float:
        """Get average latency of the last TTS request in milliseconds."""
        if not self.latency_data:
            return 0.0
        return sum(self.latency_data) / len(self.latency_data)

# Example usage:
# async def main():
#     api_key = os.getenv("ELEVENLABS_API_KEY", "your_api_key_here")
#     tts = ElevenLabsTTS(api_key, "JBFqnCBsd6RMkjVDRZzb")
#     async for chunk in tts.synthesize_stream("Hei, tämä on testiviesti.", emotion="thoughtful"):
#         print(f"Received chunk: {len(chunk.audio)} bytes, {chunk.duration_ms}ms")

# asyncio.run(main())