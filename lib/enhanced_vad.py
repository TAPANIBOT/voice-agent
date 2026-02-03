#!/usr/bin/env python3
"""
Enhanced Voice Activity Detection (VAD) for Voice Agent V2.0

Provides:
- Deepgram VAD events integration
- Energy-based local VAD fallback
- Smoothing and debouncing
- False positive filtering
"""

import time
import asyncio
from typing import Optional, Callable
from collections import deque
import structlog

logger = structlog.get_logger()


class EnhancedVAD:
    """
    Enhanced Voice Activity Detection with multiple strategies:
    
    1. Primary: Deepgram VAD events (SpeechStarted, UtteranceEnd)
    2. Fallback: Local energy-based VAD
    3. Smoothing: Debouncing to reduce false positives
    4. Filtering: Minimum duration and confidence checks
    """
    
    def __init__(
        self,
        config: dict,
        on_speech_started: Optional[Callable] = None,
        on_speech_ended: Optional[Callable] = None
    ):
        """
        Args:
            config: Configuration dict
            on_speech_started: Callback when speech starts
            on_speech_ended: Callback when speech ends
        """
        self.config = config
        self.on_speech_started = on_speech_started
        self.on_speech_ended = on_speech_ended
        
        # VAD config
        vad_config = config.get("interruption", {})
        self.vad_sensitivity = vad_config.get("vad_sensitivity", 0.7)
        self.min_speech_duration_ms = vad_config.get("min_speech_duration_ms", 200)
        self.debounce_ms = vad_config.get("debounce_ms", 50)
        
        # Energy-based VAD settings
        self.energy_threshold = 0.02  # Relative energy threshold
        self.energy_window_size = 10  # Frames to average
        
        # State
        self.is_speech_active = False
        self.speech_start_time: Optional[float] = None
        self.last_event_time: Optional[float] = None
        
        # Deepgram VAD state
        self.deepgram_vad_available = True
        self.last_deepgram_event: Optional[str] = None
        
        # Energy buffer for local VAD
        self.energy_buffer: deque = deque(maxlen=self.energy_window_size)
        
        # Stats
        self.total_speech_events = 0
        self.deepgram_events = 0
        self.local_vad_events = 0
        self.filtered_events = 0
        
        logger.info("enhanced_vad.initialized",
                   sensitivity=self.vad_sensitivity,
                   min_speech_ms=self.min_speech_duration_ms,
                   debounce_ms=self.debounce_ms)
    
    async def on_deepgram_vad_event(self, event_type: str):
        """
        Handle VAD event from Deepgram.
        
        Args:
            event_type: "SpeechStarted" or "UtteranceEnd"
        """
        current_time = time.time()
        
        self.last_deepgram_event = event_type
        self.deepgram_events += 1
        
        logger.debug("enhanced_vad.deepgram_event", event_type=event_type)
        
        # Debounce
        if self.last_event_time:
            time_since_last = (current_time - self.last_event_time) * 1000
            if time_since_last < self.debounce_ms:
                logger.debug("enhanced_vad.debounced",
                           event_type=event_type,
                           time_since_last_ms=time_since_last)
                return
        
        self.last_event_time = current_time
        
        if event_type == "SpeechStarted":
            await self._trigger_speech_started()
        
        elif event_type == "UtteranceEnd":
            await self._trigger_speech_ended()
    
    async def process_audio_frame(self, audio_data: bytes):
        """
        Process audio frame for local VAD (fallback).
        
        Used when Deepgram VAD is not available or as a supplement.
        
        Args:
            audio_data: Raw audio bytes (μ-law 8kHz)
        """
        # Calculate frame energy
        energy = self._calculate_energy(audio_data)
        self.energy_buffer.append(energy)
        
        # Get average energy
        if len(self.energy_buffer) < self.energy_window_size:
            return  # Not enough data yet
        
        avg_energy = sum(self.energy_buffer) / len(self.energy_buffer)
        
        # Check if energy exceeds threshold
        is_speech = avg_energy > self.energy_threshold
        
        current_time = time.time()
        
        # State transitions
        if is_speech and not self.is_speech_active:
            # Speech started
            self.local_vad_events += 1
            logger.debug("enhanced_vad.local_speech_start", energy=avg_energy)
            await self._trigger_speech_started()
        
        elif not is_speech and self.is_speech_active:
            # Check if speech was long enough
            if self.speech_start_time:
                duration_ms = (current_time - self.speech_start_time) * 1000
                
                if duration_ms >= self.min_speech_duration_ms:
                    # Valid speech end
                    logger.debug("enhanced_vad.local_speech_end",
                               duration_ms=duration_ms)
                    await self._trigger_speech_ended()
                else:
                    # Too short, likely noise
                    logger.debug("enhanced_vad.filtered_short",
                               duration_ms=duration_ms)
                    self.filtered_events += 1
                    self.is_speech_active = False
                    self.speech_start_time = None
    
    async def _trigger_speech_started(self):
        """Internal: Trigger speech started event."""
        if self.is_speech_active:
            return  # Already active
        
        self.is_speech_active = True
        self.speech_start_time = time.time()
        self.total_speech_events += 1
        
        logger.debug("enhanced_vad.speech_started")
        
        # Notify callback
        if self.on_speech_started:
            try:
                await self.on_speech_started()
            except Exception as e:
                logger.error("enhanced_vad.callback_error",
                           callback="on_speech_started",
                           error=str(e))
    
    async def _trigger_speech_ended(self):
        """Internal: Trigger speech ended event."""
        if not self.is_speech_active:
            return  # Not active
        
        # Check minimum duration
        if self.speech_start_time:
            duration_ms = (time.time() - self.speech_start_time) * 1000
            
            if duration_ms < self.min_speech_duration_ms:
                logger.debug("enhanced_vad.filtered_duration",
                           duration_ms=duration_ms,
                           min_ms=self.min_speech_duration_ms)
                self.filtered_events += 1
                self.is_speech_active = False
                self.speech_start_time = None
                return
        
        self.is_speech_active = False
        self.speech_start_time = None
        
        logger.debug("enhanced_vad.speech_ended")
        
        # Notify callback
        if self.on_speech_ended:
            try:
                await self.on_speech_ended()
            except Exception as e:
                logger.error("enhanced_vad.callback_error",
                           callback="on_speech_ended",
                           error=str(e))
    
    def _calculate_energy(self, audio_data: bytes) -> float:
        """
        Calculate energy of audio frame.
        
        Args:
            audio_data: Raw audio bytes (μ-law)
        
        Returns:
            Normalized energy (0.0 - 1.0)
        """
        try:
            # Simple energy calculation
            # For μ-law, this is approximate
            
            if not audio_data:
                return 0.0
            
            # Calculate sum of absolute values
            total = sum(abs(b - 128) for b in audio_data)
            
            # Normalize
            max_possible = 128 * len(audio_data)
            energy = total / max_possible if max_possible > 0 else 0.0
            
            return energy
        
        except Exception as e:
            logger.warning("enhanced_vad.energy_calc_error", error=str(e))
            return 0.0
    
    def reset(self):
        """Reset VAD state."""
        self.is_speech_active = False
        self.speech_start_time = None
        self.last_event_time = None
        self.energy_buffer.clear()
        
        logger.debug("enhanced_vad.reset")
    
    def get_state(self) -> dict:
        """Get current VAD state."""
        return {
            "is_speech_active": self.is_speech_active,
            "speech_duration_ms": (
                (time.time() - self.speech_start_time) * 1000
                if self.speech_start_time else 0
            ),
            "deepgram_vad_available": self.deepgram_vad_available,
            "last_deepgram_event": self.last_deepgram_event
        }
    
    def get_stats(self) -> dict:
        """Get VAD statistics."""
        return {
            "total_speech_events": self.total_speech_events,
            "deepgram_events": self.deepgram_events,
            "local_vad_events": self.local_vad_events,
            "filtered_events": self.filtered_events,
            "deepgram_vad_available": self.deepgram_vad_available,
            "is_speech_active": self.is_speech_active
        }


class VADSmoother:
    """
    Smooths VAD events to reduce false positives.
    
    Uses hysteresis: requires N consecutive frames to trigger
    state change.
    """
    
    def __init__(self, frames_to_trigger: int = 3):
        """
        Args:
            frames_to_trigger: Consecutive frames needed to trigger
        """
        self.frames_to_trigger = frames_to_trigger
        self.speech_frames = 0
        self.silence_frames = 0
        self.is_speech_active = False
    
    def update(self, is_speech: bool) -> Optional[str]:
        """
        Update with new frame.
        
        Args:
            is_speech: Is current frame speech?
        
        Returns:
            "started", "ended", or None
        """
        if is_speech:
            self.speech_frames += 1
            self.silence_frames = 0
            
            # Check if should trigger start
            if not self.is_speech_active and self.speech_frames >= self.frames_to_trigger:
                self.is_speech_active = True
                return "started"
        
        else:
            self.silence_frames += 1
            self.speech_frames = 0
            
            # Check if should trigger end
            if self.is_speech_active and self.silence_frames >= self.frames_to_trigger:
                self.is_speech_active = False
                return "ended"
        
        return None
    
    def reset(self):
        """Reset state."""
        self.speech_frames = 0
        self.silence_frames = 0
        self.is_speech_active = False
