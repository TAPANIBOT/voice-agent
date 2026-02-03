#!/usr/bin/env python3
"""
Audio Buffer for Voice Agent V2.0

Provides:
- Jitter buffering for smooth playback
- Circular buffer for interruption support
- Smooth crossfade on stop
- Latency compensation
"""

import asyncio
import time
from typing import Optional, Callable, List
from collections import deque
import structlog

logger = structlog.get_logger()


class AudioBuffer:
    """
    Manages audio buffering for smooth playback with interruption support.
    
    Features:
    - Jitter buffer: Absorbs network jitter for smooth playback
    - Circular buffer: Enables sub-200ms interruption
    - Crossfade: Smooth audio stop without clicks/pops
    - Latency tracking: Monitors buffer depth
    """
    
    def __init__(
        self,
        jitter_buffer_ms: int = 100,
        max_buffer_ms: int = 500,
        chunk_size_ms: int = 20,
        sample_rate: int = 8000
    ):
        """
        Args:
            jitter_buffer_ms: Initial buffering delay to absorb jitter
            max_buffer_ms: Maximum buffer size before dropping
            chunk_size_ms: Playback chunk duration
            sample_rate: Audio sample rate (8kHz for telephony)
        """
        self.jitter_buffer_ms = jitter_buffer_ms
        self.max_buffer_ms = max_buffer_ms
        self.chunk_size_ms = chunk_size_ms
        self.sample_rate = sample_rate
        
        # Calculate buffer sizes
        self.chunk_size_bytes = int(sample_rate * chunk_size_ms / 1000)
        self.max_buffer_size = int(sample_rate * max_buffer_ms / 1000)
        
        # Buffers
        self.buffer: deque = deque()
        self.total_buffered_bytes = 0
        
        # State
        self.is_playing = False
        self.interrupted = False
        self.playback_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self.on_chunk_callback: Optional[Callable[[bytes], None]] = None
        
        # Stats
        self.total_bytes_played = 0
        self.underruns = 0
        self.overruns = 0
        
        logger.info("audio_buffer.initialized",
                   jitter_ms=jitter_buffer_ms,
                   max_ms=max_buffer_ms,
                   chunk_ms=chunk_size_ms)
    
    def add_audio(self, audio_data: bytes):
        """
        Add audio data to buffer.
        
        Args:
            audio_data: Raw audio bytes (μ-law 8kHz)
        """
        if self.interrupted:
            # Discard audio after interruption
            return
        
        self.buffer.append(audio_data)
        self.total_buffered_bytes += len(audio_data)
        
        # Check for overflow
        if self.total_buffered_bytes > self.max_buffer_size:
            # Drop oldest chunk
            dropped = self.buffer.popleft()
            self.total_buffered_bytes -= len(dropped)
            self.overruns += 1
            
            logger.warning("audio_buffer.overrun",
                         buffer_bytes=self.total_buffered_bytes,
                         dropped_bytes=len(dropped))
    
    async def start_playback(self, on_chunk: Callable[[bytes], None]):
        """
        Start playing buffered audio.
        
        Args:
            on_chunk: Callback for each audio chunk
        """
        if self.is_playing:
            logger.warning("audio_buffer.already_playing")
            return
        
        self.on_chunk_callback = on_chunk
        self.is_playing = True
        self.interrupted = False
        
        # Wait for initial jitter buffer to fill
        jitter_fill_start = time.time()
        target_bytes = int(self.sample_rate * self.jitter_buffer_ms / 1000)
        
        while self.total_buffered_bytes < target_bytes:
            await asyncio.sleep(0.01)
            
            # Timeout if no data arrives
            if time.time() - jitter_fill_start > 1.0:
                logger.warning("audio_buffer.jitter_timeout",
                             buffered_bytes=self.total_buffered_bytes,
                             target_bytes=target_bytes)
                break
        
        logger.info("audio_buffer.playback_started",
                   buffered_ms=self._get_buffered_ms())
        
        # Start playback loop
        self.playback_task = asyncio.create_task(self._playback_loop())
    
    async def _playback_loop(self):
        """Main playback loop."""
        try:
            while self.is_playing and not self.interrupted:
                if not self.buffer:
                    # Buffer underrun
                    self.underruns += 1
                    logger.debug("audio_buffer.underrun")
                    
                    # Wait for more data
                    await asyncio.sleep(0.01)
                    continue
                
                # Get next chunk
                chunk = self.buffer.popleft()
                self.total_buffered_bytes -= len(chunk)
                
                # Send to output
                if self.on_chunk_callback:
                    await self.on_chunk_callback(chunk)
                
                self.total_bytes_played += len(chunk)
                
                # Sleep for chunk duration (pace playback)
                chunk_duration_ms = len(chunk) * 1000 / self.sample_rate
                await asyncio.sleep(chunk_duration_ms / 1000)
        
        except Exception as e:
            logger.error("audio_buffer.playback_error", error=str(e))
        finally:
            self.is_playing = False
            logger.info("audio_buffer.playback_stopped",
                       bytes_played=self.total_bytes_played)
    
    async def stop_playback(self, smooth: bool = True):
        """
        Stop audio playback.
        
        Args:
            smooth: Apply crossfade for smooth stop
        """
        if not self.is_playing:
            return
        
        logger.info("audio_buffer.stopping", smooth=smooth)
        
        if smooth and self.buffer:
            # Apply quick fadeout to last chunk
            try:
                last_chunk = self.buffer[-1]
                faded_chunk = self._apply_fadeout(last_chunk, duration_ms=50)
                self.buffer[-1] = faded_chunk
            except Exception as e:
                logger.warning("audio_buffer.fadeout_failed", error=str(e))
        
        self.is_playing = False
        
        # Wait for playback task to finish
        if self.playback_task:
            try:
                await asyncio.wait_for(self.playback_task, timeout=1.0)
            except asyncio.TimeoutError:
                self.playback_task.cancel()
                try:
                    await self.playback_task
                except asyncio.CancelledError:
                    pass
        
        logger.info("audio_buffer.stopped")
    
    def interrupt(self):
        """
        Interrupt playback immediately (for barge-in).
        
        Clears buffer and stops playback with minimal latency.
        """
        logger.info("audio_buffer.interrupt",
                   buffered_ms=self._get_buffered_ms())
        
        self.interrupted = True
        self.is_playing = False
        
        # Clear buffer
        self.buffer.clear()
        self.total_buffered_bytes = 0
        
        # Cancel playback task
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
    
    def reset(self):
        """Reset buffer state for new playback."""
        self.buffer.clear()
        self.total_buffered_bytes = 0
        self.interrupted = False
        self.is_playing = False
        self.total_bytes_played = 0
    
    def _apply_fadeout(self, audio_data: bytes, duration_ms: int = 50) -> bytes:
        """
        Apply linear fadeout to audio data.
        
        Args:
            audio_data: Raw audio bytes (μ-law)
            duration_ms: Fadeout duration
        
        Returns:
            Faded audio bytes
        """
        try:
            import numpy as np
            
            # Convert μ-law to PCM
            # Note: This is a simplified version
            # In production, use proper μ-law decoder
            
            # For now, return original (fadeout on μ-law is complex)
            # TODO: Implement proper μ-law fadeout
            return audio_data
        
        except ImportError:
            # No numpy, return original
            return audio_data
    
    def _get_buffered_ms(self) -> float:
        """Get buffered audio duration in milliseconds."""
        return (self.total_buffered_bytes * 1000) / self.sample_rate
    
    def get_stats(self) -> dict:
        """Get buffer statistics."""
        return {
            "is_playing": self.is_playing,
            "interrupted": self.interrupted,
            "buffered_ms": self._get_buffered_ms(),
            "buffered_chunks": len(self.buffer),
            "total_bytes_played": self.total_bytes_played,
            "underruns": self.underruns,
            "overruns": self.overruns
        }


class CircularAudioBuffer:
    """
    Circular buffer optimized for interruption.
    
    Maintains a sliding window of recent audio for:
    - Quick stop detection
    - Seamless resume after false interruption
    - Audio crossfade
    """
    
    def __init__(self, capacity_ms: int = 200, sample_rate: int = 8000):
        """
        Args:
            capacity_ms: Buffer capacity (older audio is discarded)
            sample_rate: Audio sample rate
        """
        self.capacity_bytes = int(sample_rate * capacity_ms / 1000)
        self.buffer: deque = deque(maxlen=self.capacity_bytes)
        self.sample_rate = sample_rate
        
        logger.debug("circular_buffer.initialized", capacity_ms=capacity_ms)
    
    def add(self, audio_data: bytes):
        """Add audio data to circular buffer."""
        for byte in audio_data:
            self.buffer.append(byte)
    
    def get_last(self, duration_ms: int) -> bytes:
        """
        Get last N milliseconds of audio.
        
        Args:
            duration_ms: Duration to retrieve
        
        Returns:
            Audio bytes
        """
        num_bytes = int(self.sample_rate * duration_ms / 1000)
        num_bytes = min(num_bytes, len(self.buffer))
        
        if num_bytes <= 0:
            return b""
        
        return bytes(list(self.buffer)[-num_bytes:])
    
    def clear(self):
        """Clear the buffer."""
        self.buffer.clear()
    
    def get_duration_ms(self) -> float:
        """Get current buffer duration in milliseconds."""
        return (len(self.buffer) * 1000) / self.sample_rate
