#!/usr/bin/env python3
"""
Interruption Handler for Voice Agent V2.0

Enables sub-200ms barge-in capability with:
- State-based interruption management
- VAD-based speech detection
- Audio playback control
- Speech queue management
"""

import asyncio
import time
from typing import Optional, Callable, Dict, Any
from enum import Enum
import structlog

logger = structlog.get_logger()


class InterruptionState(Enum):
    """Agent conversation state."""
    LISTENING = "listening"  # Agent listening, user can speak
    PROCESSING = "processing"  # Generating response
    SPEAKING = "speaking"  # Agent speaking (interruptible)
    INTERRUPTED = "interrupted"  # User barged in


class SpeechQueue:
    """
    Manages pending agent utterances.
    
    When user interrupts, clears queue to avoid speaking
    over the user.
    """
    
    def __init__(self):
        self.queue: list = []
        self.current_speech_id: Optional[str] = None
        self.next_speech_id = 0
    
    def add(self, text: str, priority: int = 0) -> str:
        """
        Add speech to queue.
        
        Args:
            text: Text to speak
            priority: Higher priority speaks first
        
        Returns:
            Speech ID
        """
        speech_id = f"speech_{self.next_speech_id}"
        self.next_speech_id += 1
        
        self.queue.append({
            "id": speech_id,
            "text": text,
            "priority": priority,
            "queued_at": time.time()
        })
        
        # Sort by priority
        self.queue.sort(key=lambda x: x["priority"], reverse=True)
        
        logger.debug("speech_queue.added",
                    speech_id=speech_id,
                    queue_size=len(self.queue))
        
        return speech_id
    
    def get_next(self) -> Optional[Dict[str, Any]]:
        """Get next speech from queue."""
        if self.queue:
            speech = self.queue.pop(0)
            self.current_speech_id = speech["id"]
            return speech
        return None
    
    def clear(self):
        """Clear all pending speech."""
        cleared_count = len(self.queue)
        self.queue.clear()
        
        if cleared_count > 0:
            logger.info("speech_queue.cleared", count=cleared_count)
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.queue) == 0
    
    def size(self) -> int:
        """Get queue size."""
        return len(self.queue)


class AudioPlaybackController:
    """
    Controls audio playback with interruption support.
    
    Can stop playback mid-word for barge-in.
    """
    
    def __init__(self, audio_buffer: Any):
        """
        Args:
            audio_buffer: AudioBuffer instance
        """
        self.audio_buffer = audio_buffer
        self.is_playing = False
        self.current_playback_id: Optional[str] = None
        self.playback_start_time: Optional[float] = None
    
    async def play(
        self,
        playback_id: str,
        on_audio: Callable[[bytes], None]
    ):
        """
        Start audio playback.
        
        Args:
            playback_id: Unique playback identifier
            on_audio: Callback for audio chunks
        """
        self.is_playing = True
        self.current_playback_id = playback_id
        self.playback_start_time = time.time()
        
        logger.info("playback.started", playback_id=playback_id)
        
        await self.audio_buffer.start_playback(on_audio)
    
    async def stop(self, smooth: bool = True):
        """
        Stop current playback.
        
        Args:
            smooth: Apply crossfade for smooth stop
        """
        if not self.is_playing:
            return
        
        stop_latency_start = time.time()
        
        await self.audio_buffer.stop_playback(smooth=smooth)
        
        stop_latency_ms = (time.time() - stop_latency_start) * 1000
        
        if self.playback_start_time:
            played_duration_ms = (time.time() - self.playback_start_time) * 1000
        else:
            played_duration_ms = 0
        
        logger.info("playback.stopped",
                   playback_id=self.current_playback_id,
                   stop_latency_ms=stop_latency_ms,
                   played_duration_ms=played_duration_ms)
        
        self.is_playing = False
        self.current_playback_id = None
        self.playback_start_time = None
        
        return stop_latency_ms
    
    def interrupt(self):
        """Interrupt playback immediately (for barge-in)."""
        if not self.is_playing:
            return
        
        interrupt_start = time.time()
        
        self.audio_buffer.interrupt()
        
        interrupt_latency_ms = (time.time() - interrupt_start) * 1000
        
        logger.info("playback.interrupted",
                   playback_id=self.current_playback_id,
                   interrupt_latency_ms=interrupt_latency_ms)
        
        self.is_playing = False
        self.current_playback_id = None
        self.playback_start_time = None
        
        return interrupt_latency_ms
    
    def get_state(self) -> dict:
        """Get playback state."""
        return {
            "is_playing": self.is_playing,
            "playback_id": self.current_playback_id,
            "playback_duration_ms": (
                (time.time() - self.playback_start_time) * 1000
                if self.playback_start_time else 0
            )
        }


class InterruptionHandler:
    """
    Main interruption handler for sub-200ms barge-in.
    
    Manages conversation state and handles user interruptions:
    1. Detects user speech via VAD
    2. Stops agent playback immediately
    3. Clears pending speech queue
    4. Transitions to LISTENING state
    
    Target: <200ms from speech detection to audio stop
    """
    
    def __init__(
        self,
        vad: Any,
        playback_controller: AudioPlaybackController,
        config: dict
    ):
        """
        Args:
            vad: EnhancedVAD instance
            playback_controller: AudioPlaybackController instance
            config: Configuration dict
        """
        self.vad = vad
        self.playback_controller = playback_controller
        self.config = config
        
        # State
        self.state = InterruptionState.LISTENING
        self.speech_queue = SpeechQueue()
        
        # Interruption config
        int_config = config.get("interruption", {})
        self.enabled = int_config.get("enabled", True)
        self.min_speech_duration_ms = int_config.get("min_speech_duration_ms", 200)
        self.stop_latency_target_ms = int_config.get("stop_latency_target_ms", 150)
        self.debounce_ms = int_config.get("debounce_ms", 50)
        self.require_confident_speech = int_config.get("require_confident_speech", True)
        
        # Callbacks
        self.on_interruption: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None
        
        # Stats
        self.total_interruptions = 0
        self.interruption_latencies: list = []
        self.false_positives = 0
        
        # Debounce tracking
        self.last_vad_event_time: Optional[float] = None
        self.speech_start_time: Optional[float] = None
        
        logger.info("interruption_handler.initialized",
                   enabled=self.enabled,
                   min_speech_ms=self.min_speech_duration_ms,
                   target_latency_ms=self.stop_latency_target_ms)
    
    def set_callbacks(
        self,
        on_interruption: Optional[Callable] = None,
        on_state_change: Optional[Callable] = None
    ):
        """Set event callbacks."""
        self.on_interruption = on_interruption
        self.on_state_change = on_state_change
    
    async def on_speech_started(self):
        """
        Handle VAD speech start event.
        
        Called when user starts speaking.
        """
        if not self.enabled:
            return
        
        current_time = time.time()
        
        # Debounce
        if self.last_vad_event_time:
            time_since_last = (current_time - self.last_vad_event_time) * 1000
            if time_since_last < self.debounce_ms:
                logger.debug("interruption.debounced",
                           time_since_last_ms=time_since_last)
                return
        
        self.last_vad_event_time = current_time
        self.speech_start_time = current_time
        
        logger.debug("interruption.speech_started", state=self.state.value)
        
        # Handle based on current state
        if self.state == InterruptionState.SPEAKING:
            # User is interrupting agent
            await self._handle_barge_in()
        
        elif self.state == InterruptionState.LISTENING:
            # Normal user speech
            pass
    
    async def on_speech_ended(self):
        """
        Handle VAD speech end event.
        
        Called when user stops speaking.
        """
        if not self.enabled:
            return
        
        current_time = time.time()
        
        # Calculate speech duration
        if self.speech_start_time:
            speech_duration_ms = (current_time - self.speech_start_time) * 1000
            
            # Check if speech was long enough to be confident
            if self.require_confident_speech and speech_duration_ms < self.min_speech_duration_ms:
                logger.debug("interruption.speech_too_short",
                           duration_ms=speech_duration_ms)
                self.false_positives += 1
        
        self.speech_start_time = None
        
        logger.debug("interruption.speech_ended", state=self.state.value)
    
    async def _handle_barge_in(self):
        """
        Handle user barge-in (interruption).
        
        Critical path - must be <200ms total:
        1. Stop playback: ~50-100ms
        2. Clear queue: <1ms
        3. State transition: <1ms
        """
        barge_in_start = time.time()
        
        logger.info("interruption.barge_in_detected")
        
        # Step 1: Stop playback immediately
        stop_latency_ms = self.playback_controller.interrupt()
        
        # Step 2: Clear pending speech
        self.speech_queue.clear()
        
        # Step 3: Transition state
        await self._transition_state(InterruptionState.INTERRUPTED)
        
        # Calculate total latency
        total_latency_ms = (time.time() - barge_in_start) * 1000
        
        self.total_interruptions += 1
        self.interruption_latencies.append(total_latency_ms)
        
        # Keep last 100 latencies
        if len(self.interruption_latencies) > 100:
            self.interruption_latencies = self.interruption_latencies[-100:]
        
        logger.info("interruption.barge_in_complete",
                   total_latency_ms=total_latency_ms,
                   stop_latency_ms=stop_latency_ms,
                   target_ms=self.stop_latency_target_ms,
                   met_target=total_latency_ms < self.stop_latency_target_ms)
        
        # Notify callback
        if self.on_interruption:
            await self.on_interruption({
                "total_latency_ms": total_latency_ms,
                "stop_latency_ms": stop_latency_ms
            })
    
    async def _transition_state(self, new_state: InterruptionState):
        """Transition to new state."""
        old_state = self.state
        self.state = new_state
        
        logger.info("interruption.state_change",
                   from_state=old_state.value,
                   to_state=new_state.value)
        
        # Notify callback
        if self.on_state_change:
            await self.on_state_change(old_state, new_state)
    
    async def start_listening(self):
        """Enter LISTENING state."""
        await self._transition_state(InterruptionState.LISTENING)
    
    async def start_processing(self):
        """Enter PROCESSING state (generating response)."""
        await self._transition_state(InterruptionState.PROCESSING)
    
    async def start_speaking(self):
        """Enter SPEAKING state (agent talking)."""
        await self._transition_state(InterruptionState.SPEAKING)
    
    def queue_speech(self, text: str, priority: int = 0) -> str:
        """
        Queue speech for playback.
        
        Args:
            text: Text to speak
            priority: Priority (higher = first)
        
        Returns:
            Speech ID
        """
        return self.speech_queue.add(text, priority)
    
    def get_next_speech(self) -> Optional[Dict[str, Any]]:
        """Get next speech from queue."""
        return self.speech_queue.get_next()
    
    def get_state(self) -> InterruptionState:
        """Get current state."""
        return self.state
    
    def get_stats(self) -> dict:
        """Get interruption statistics."""
        import statistics
        
        if self.interruption_latencies:
            latencies = sorted(self.interruption_latencies)
            count = len(latencies)
            
            latency_stats = {
                "mean": statistics.mean(latencies),
                "p50": latencies[int(count * 0.5)],
                "p95": latencies[int(count * 0.95)] if count > 1 else 0,
                "p99": latencies[int(count * 0.99)] if count > 1 else 0,
                "min": min(latencies),
                "max": max(latencies)
            }
        else:
            latency_stats = {}
        
        return {
            "enabled": self.enabled,
            "state": self.state.value,
            "total_interruptions": self.total_interruptions,
            "false_positives": self.false_positives,
            "queue_size": self.speech_queue.size(),
            "latency_stats": latency_stats,
            "playback_state": self.playback_controller.get_state()
        }
