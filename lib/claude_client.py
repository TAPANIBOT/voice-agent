import asyncio
import aiohttp
import json
from typing import AsyncIterator, List

class ClaudeStreaming:
    def __init__(self, api_key: str, model: str = "claude-haiku-3.5"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.session = aiohttp.ClientSession()
        self.latency = 0

    async def generate_stream(self, messages: List[dict], system: str) -> AsyncIterator[str]:
        """Stream responses chunk-by-chunk using Server-Sent Events."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "anthropic-version": "2023-06-01",
            "x-api-key": self.api_key,
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "system": system,
            "max_tokens": 1024,
            "stream": True,
        }
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.session.post(self.base_url, headers=headers, json=data) as response:
                async for line in response.content:
                    if line.startswith(b'data: '):
                        chunk = line[6:].decode('utf-8').strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            content = data.get("content", [{}])[0].get("text", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                
                self.latency = (asyncio.get_event_loop().time() - start_time) * 1000
                
        except aiohttp.ClientError as e:
            print(f"Error in streaming: {e}")
            yield "Error in streaming response"

    async def generate_complete(self, messages: List[dict], system: str) -> str:
        """Get complete response without streaming."""
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": self.api_key,
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "system": system,
            "max_tokens": 1024,
            "stream": False,
        }
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.session.post(self.base_url, headers=headers, json=data) as response:
                response_data = await response.json()
                self.latency = (asyncio.get_event_loop().time() - start_time) * 1000
                return response_data.get("content", [{}])[0].get("text", "")
        except aiohttp.ClientError as e:
            print(f"Error in complete response: {e}")
            return "Error in complete response"

    def get_latency_ms(self) -> float:
        return self.latency

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()