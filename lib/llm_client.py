#!/usr/bin/env python3
"""
LLM Client for Voice Agent V2.0

Handles streaming text generation from Claude/Anthropic API with:
- Streaming support for low latency
- Retry logic with exponential backoff
- Rate limiting
- Token usage tracking
- Context building from conversation history
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, AsyncGenerator
import structlog
from anthropic import AsyncAnthropic, AsyncStream
from anthropic.types import MessageStreamEvent

logger = structlog.get_logger()


class LLMClient:
    """
    Client for Claude/Anthropic streaming API.
    
    Optimized for conversational voice with:
    - Fast first-token latency
    - Short, natural responses
    - Context-aware generation
    """
    
    def __init__(self, api_key: str, config: dict):
        """
        Args:
            api_key: Anthropic API key
            config: Configuration dict
        """
        self.client = AsyncAnthropic(api_key=api_key)
        self.config = config
        
        # LLM settings
        llm_config = config.get("streaming", {})
        self.model = llm_config.get("llm_model", "claude-3-7-sonnet-20250219")
        self.max_tokens = llm_config.get("llm_max_tokens", 150)
        self.temperature = llm_config.get("llm_temperature", 0.7)
        
        # Conversation settings
        conv_config = config.get("conversation", {})
        self.system_prompt = conv_config.get("default_context", "").strip()
        self.max_history_turns = conv_config.get("max_history_turns", 20)
        
        # Rate limiting
        self.requests_this_minute = 0
        self.minute_start = time.time()
        self.rate_limit_per_minute = config.get("rate_limit", {}).get("requests_per_minute", 60)
        
        # Retry settings
        retry_config = config.get("retry_policy", {})
        self.max_attempts = retry_config.get("max_attempts", 3)
        self.initial_backoff_ms = retry_config.get("initial_backoff_ms", 100)
        self.max_backoff_ms = retry_config.get("max_backoff_ms", 2000)
        self.exponential_base = retry_config.get("exponential_base", 2)
        
        # Stats
        self.total_requests = 0
        self.total_tokens_used = 0
        self.total_errors = 0
        
        logger.info("llm_client.initialized",
                   model=self.model,
                   max_tokens=self.max_tokens,
                   temperature=self.temperature)
    
    def _build_messages(
        self,
        conversation_context: List[Dict[str, str]],
        user_message: str
    ) -> List[Dict[str, str]]:
        """
        Build messages array from conversation context.
        
        Args:
            conversation_context: List of previous turns
            user_message: Current user message
        
        Returns:
            Messages formatted for Claude API
        """
        messages = []
        
        # Add conversation history (sliding window)
        for turn in conversation_context[-self.max_history_turns:]:
            role = turn.get("role")
            content = turn.get("content", "")
            
            if role in ["user", "assistant"] and content.strip():
                messages.append({
                    "role": role,
                    "content": content
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        current_time = time.time()
        
        # Reset counter every minute
        if current_time - self.minute_start > 60:
            self.requests_this_minute = 0
            self.minute_start = current_time
        
        # Check limit
        if self.requests_this_minute >= self.rate_limit_per_minute:
            wait_time = 60 - (current_time - self.minute_start)
            if wait_time > 0:
                logger.warning("llm_client.rate_limited",
                             wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
                self.requests_this_minute = 0
                self.minute_start = time.time()
        
        self.requests_this_minute += 1
    
    async def generate_stream(
        self,
        conversation_context: List[Dict[str, str]],
        user_message: str
    ) -> AsyncGenerator[str, None]:
        """
        Generate response with streaming (yields tokens as they arrive).
        
        Args:
            conversation_context: Conversation history
            user_message: Current user message
        
        Yields:
            Response tokens
        """
        await self._check_rate_limit()
        
        messages = self._build_messages(conversation_context, user_message)
        
        logger.info("llm_client.generate_stream",
                   message_count=len(messages),
                   user_message_length=len(user_message))
        
        # Retry logic
        for attempt in range(self.max_attempts):
            try:
                start_time = time.time()
                first_token_time = None
                token_count = 0
                
                async with self.client.messages.stream(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=self.system_prompt if self.system_prompt else None,
                    messages=messages
                ) as stream:
                    async for text in stream.text_stream:
                        if first_token_time is None:
                            first_token_time = time.time()
                            first_token_latency_ms = (first_token_time - start_time) * 1000
                            logger.debug("llm_client.first_token",
                                       latency_ms=first_token_latency_ms,
                                       attempt=attempt + 1)
                        
                        token_count += 1
                        yield text
                
                # Success
                total_time_ms = (time.time() - start_time) * 1000
                self.total_requests += 1
                self.total_tokens_used += token_count
                
                logger.info("llm_client.generate_complete",
                           tokens=token_count,
                           total_time_ms=total_time_ms,
                           attempt=attempt + 1)
                
                return
            
            except Exception as e:
                self.total_errors += 1
                
                # Check if should retry
                if attempt < self.max_attempts - 1:
                    backoff_ms = min(
                        self.initial_backoff_ms * (self.exponential_base ** attempt),
                        self.max_backoff_ms
                    )
                    
                    logger.warning("llm_client.retry",
                                 attempt=attempt + 1,
                                 error=str(e),
                                 backoff_ms=backoff_ms)
                    
                    await asyncio.sleep(backoff_ms / 1000)
                else:
                    logger.error("llm_client.failed",
                               attempts=self.max_attempts,
                               error=str(e))
                    raise
    
    async def generate(
        self,
        conversation_context: List[Dict[str, str]],
        user_message: str
    ) -> str:
        """
        Generate complete response (non-streaming fallback).
        
        Args:
            conversation_context: Conversation history
            user_message: Current user message
        
        Returns:
            Complete response text
        """
        await self._check_rate_limit()
        
        messages = self._build_messages(conversation_context, user_message)
        
        logger.info("llm_client.generate",
                   message_count=len(messages),
                   user_message_length=len(user_message))
        
        # Retry logic
        for attempt in range(self.max_attempts):
            try:
                start_time = time.time()
                
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=self.system_prompt if self.system_prompt else None,
                    messages=messages
                )
                
                text = response.content[0].text
                total_time_ms = (time.time() - start_time) * 1000
                
                self.total_requests += 1
                self.total_tokens_used += response.usage.output_tokens
                
                logger.info("llm_client.generate_complete",
                           tokens=response.usage.output_tokens,
                           total_time_ms=total_time_ms,
                           attempt=attempt + 1)
                
                return text
            
            except Exception as e:
                self.total_errors += 1
                
                # Check if should retry
                if attempt < self.max_attempts - 1:
                    backoff_ms = min(
                        self.initial_backoff_ms * (self.exponential_base ** attempt),
                        self.max_backoff_ms
                    )
                    
                    logger.warning("llm_client.retry",
                                 attempt=attempt + 1,
                                 error=str(e),
                                 backoff_ms=backoff_ms)
                    
                    await asyncio.sleep(backoff_ms / 1000)
                else:
                    logger.error("llm_client.failed",
                               attempts=self.max_attempts,
                               error=str(e))
                    raise
        
        raise RuntimeError("Failed to generate response")
    
    def get_stats(self) -> dict:
        """Get client statistics."""
        return {
            "total_requests": self.total_requests,
            "total_tokens_used": self.total_tokens_used,
            "total_errors": self.total_errors,
            "requests_this_minute": self.requests_this_minute,
            "error_rate": self.total_errors / max(self.total_requests, 1)
        }
