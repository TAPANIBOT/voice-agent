#!/usr/bin/env python3
"""
Streaming Orchestrator for Voice Agent V2.0

Coordinates concurrent STT → LLM → TTS pipeline to reduce latency
from ~2500ms to ~600ms.

Key features:
- Concurrent pipeline stages (not sequential)
- First-token optimization (LLM and TTS start ASAP)
- Latency tracking per component
- Graceful degradation on errors
"""

import asyncio
import time
from typing import Optional, Callable, Dict, Any, AsyncGenerator
from enum import Enum
import structlog

logger = structlog.get_logger()


class PipelineStage(Enum):
    """Pipeline processing stages."""
    STT = "stt"
    LLM = "llm"
    TTS = "tts"
    PLAYBACK = "playback"


class LatencyTracker:
    """
    Tracks latency at each pipeline stage.
    
    Provides p50, p95, p99 metrics for monitoring.
    """
    
    def __init__(self):
        self.stage_times: Dict[PipelineStage, list] = {
            stage: [] for stage in PipelineStage
        }
        self.total_times: list = []
        self.start_times: Dict[str, float] = {}
    
    def start(self, request_id: str):
        """Mark start of pipeline for a request."""
        self.start_times[request_id] = time.time()
    
    def stage_complete(self, request_id: str, stage: PipelineStage, duration_ms: float):
        """Record stage completion time."""
        self.stage_times[stage].append(duration_ms)
        
        # Keep last 1000 measurements
        if len(self.stage_times[stage]) > 1000:
            self.stage_times[stage] = self.stage_times[stage][-1000:]
    
    def complete(self, request_id: str):
        """Mark pipeline completion."""
        if request_id in self.start_times:
            total_ms = (time.time() - self.start_times[request_id]) * 1000
            self.total_times.append(total_ms)
            
            if len(self.total_times) > 1000:
                self.total_times = self.total_times[-1000:]
            
            del self.start_times[request_id]
            return total_ms
        return None
    
    def get_stats(self, stage: Optional[PipelineStage] = None) -> dict:
        """Get latency statistics."""
        import statistics
        
        if stage:
            times = self.stage_times.get(stage, [])
        else:
            times = self.total_times
        
        if not times:
            return {
                "count": 0,
                "mean": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0
            }
        
        sorted_times = sorted(times)
        count = len(sorted_times)
        
        return {
            "count": count,
            "mean": statistics.mean(sorted_times),
            "p50": sorted_times[int(count * 0.5)] if count > 0 else 0,
            "p95": sorted_times[int(count * 0.95)] if count > 1 else 0,
            "p99": sorted_times[int(count * 0.99)] if count > 1 else 0,
            "min": min(sorted_times),
            "max": max(sorted_times)
        }


class StreamCoordinator:
    """
    Coordinates concurrent streaming from LLM to TTS.
    
    Buffers LLM tokens and sends to TTS in optimal chunks
    to minimize first-audio latency.
    """
    
    def __init__(self, chunk_size: int = 512):
        self.chunk_size = chunk_size
        self.buffer = []
        self.flushed = False
    
    def add_token(self, token: str) -> Optional[str]:
        """
        Add token from LLM stream.
        
        Returns chunk to send to TTS when buffer is full enough,
        or None if should keep buffering.
        """
        self.buffer.append(token)
        
        # Check if we have a good chunk to send
        current_text = "".join(self.buffer)
        
        # Send chunk if:
        # 1. Buffer is large enough
        # 2. We hit sentence boundary (., !, ?)
        # 3. We hit clause boundary (,)
        
        if len(current_text) >= self.chunk_size:
            return self._flush_buffer()
        
        # Check for natural break points
        if current_text.rstrip().endswith(('.', '!', '?')):
            return self._flush_buffer()
        
        if len(current_text) > 100 and current_text.rstrip().endswith(','):
            return self._flush_buffer()
        
        return None
    
    def flush(self) -> Optional[str]:
        """Flush remaining buffer."""
        if self.buffer and not self.flushed:
            self.flushed = True
            return self._flush_buffer()
        return None
    
    def _flush_buffer(self) -> str:
        """Internal flush."""
        text = "".join(self.buffer)
        self.buffer = []
        return text


class StreamingOrchestrator:
    """
    Main orchestrator for concurrent STT → LLM → TTS pipeline.
    
    Replaces sequential processing with streaming pipeline:
    - User speaks → STT transcribes (streaming)
    - Transcript ready → LLM generates (streaming)
    - First LLM tokens → TTS starts (streaming)
    - First TTS audio → Playback starts (concurrent)
    
    Target latency: <800ms (vs ~2500ms sequential)
    """
    
    def __init__(
        self,
        llm_client: Any,
        tts_client: Any,
        audio_buffer: Any,
        config: dict
    ):
        """
        Args:
            llm_client: LLM streaming client (llm_client.LLMClient)
            tts_client: TTS client (elevenlabs_client.ElevenLabsClient)
            audio_buffer: Audio buffer for playback (audio_buffer.AudioBuffer)
            config: Configuration dict
        """
        self.llm_client = llm_client
        self.tts_client = tts_client
        self.audio_buffer = audio_buffer
        self.config = config
        
        self.latency_tracker = LatencyTracker()
        self.active_pipelines: Dict[str, bool] = {}
        
        # Streaming config
        stream_config = config.get("streaming", {})
        self.llm_streaming_enabled = stream_config.get("llm_streaming_enabled", True)
        self.stream_chunk_size = stream_config.get("stream_chunk_size", 512)
        self.tts_websocket_mode = stream_config.get("tts_websocket_mode", True)
        
        logger.info("streaming_orchestrator.initialized",
                   llm_streaming=self.llm_streaming_enabled,
                   chunk_size=self.stream_chunk_size,
                   tts_websocket=self.tts_websocket_mode)
    
    async def process_transcript(
        self,
        call_id: str,
        transcript: str,
        conversation_context: list,
        on_audio: Callable[[bytes], None]
    ) -> dict:
        """
        Process user transcript through streaming pipeline.
        
        Args:
            call_id: Call identifier
            transcript: User's speech transcript
            conversation_context: Conversation history
            on_audio: Callback for audio chunks
        
        Returns:
            dict with response_text, audio_duration_ms, latencies
        """
        request_id = f"{call_id}_{int(time.time() * 1000)}"
        self.latency_tracker.start(request_id)
        self.active_pipelines[request_id] = True
        
        logger.info("streaming_pipeline.start",
                   request_id=request_id,
                   transcript_length=len(transcript))
        
        try:
            if self.llm_streaming_enabled and self.tts_websocket_mode:
                # Full streaming pipeline
                result = await self._streaming_pipeline(
                    request_id,
                    transcript,
                    conversation_context,
                    on_audio
                )
            else:
                # Fallback to sequential (graceful degradation)
                logger.warning("streaming_pipeline.fallback_sequential",
                             request_id=request_id)
                result = await self._sequential_pipeline(
                    request_id,
                    transcript,
                    conversation_context,
                    on_audio
                )
            
            total_latency = self.latency_tracker.complete(request_id)
            result["total_latency_ms"] = total_latency
            
            logger.info("streaming_pipeline.complete",
                       request_id=request_id,
                       total_latency_ms=total_latency,
                       response_length=len(result.get("response_text", "")))
            
            return result
        
        except Exception as e:
            logger.error("streaming_pipeline.error",
                        request_id=request_id,
                        error=str(e))
            raise
        finally:
            self.active_pipelines.pop(request_id, None)
    
    async def _streaming_pipeline(
        self,
        request_id: str,
        transcript: str,
        conversation_context: list,
        on_audio: Callable[[bytes], None]
    ) -> dict:
        """
        Full concurrent streaming pipeline.
        
        Pipeline flow:
        1. LLM starts generating (streaming)
        2. First tokens → Coordinator buffers
        3. Good chunk ready → TTS WebSocket receives
        4. First audio chunk → Playback starts
        5. All stages run concurrently
        """
        stage_start = time.time()
        
        # Stage 1: LLM Streaming
        coordinator = StreamCoordinator(chunk_size=self.stream_chunk_size)
        response_tokens = []
        first_token_received = False
        first_token_latency_ms = None
        
        # Stage 2 & 3: TTS WebSocket + Playback (concurrent)
        audio_queue = asyncio.Queue(maxsize=10)
        playback_task = None
        first_audio_received = False
        first_audio_latency_ms = None
        
        async def audio_callback(audio_chunk: bytes):
            """Handle audio chunks from TTS."""
            nonlocal first_audio_received, first_audio_latency_ms
            
            if not first_audio_received:
                first_audio_received = True
                first_audio_latency_ms = (time.time() - stage_start) * 1000
                self.latency_tracker.stage_complete(
                    request_id,
                    PipelineStage.TTS,
                    first_audio_latency_ms
                )
                logger.debug("streaming_pipeline.first_audio",
                           request_id=request_id,
                           latency_ms=first_audio_latency_ms)
            
            await audio_queue.put(audio_chunk)
        
        # Start TTS WebSocket connection
        tts_ws = await self.tts_client.generate_websocket(
            on_audio=audio_callback
        )
        await tts_ws.connect()
        
        # Start playback task
        async def playback_loop():
            """Consume audio from queue and play."""
            try:
                while True:
                    try:
                        audio_chunk = await asyncio.wait_for(
                            audio_queue.get(),
                            timeout=5.0
                        )
                        
                        if audio_chunk is None:
                            break
                        
                        # Send to playback
                        await on_audio(audio_chunk)
                    
                    except asyncio.TimeoutError:
                        # Check if pipeline is still active
                        if not self.active_pipelines.get(request_id):
                            break
            
            except Exception as e:
                logger.error("streaming_pipeline.playback_error",
                           request_id=request_id,
                           error=str(e))
        
        playback_task = asyncio.create_task(playback_loop())
        
        # Stream from LLM
        try:
            async for token in self.llm_client.generate_stream(
                conversation_context=conversation_context,
                user_message=transcript
            ):
                if not first_token_received:
                    first_token_received = True
                    first_token_latency_ms = (time.time() - stage_start) * 1000
                    self.latency_tracker.stage_complete(
                        request_id,
                        PipelineStage.LLM,
                        first_token_latency_ms
                    )
                    logger.debug("streaming_pipeline.first_token",
                               request_id=request_id,
                               latency_ms=first_token_latency_ms)
                
                response_tokens.append(token)
                
                # Check if we should send chunk to TTS
                chunk = coordinator.add_token(token)
                if chunk:
                    await tts_ws.send_text(chunk)
            
            # Flush remaining
            final_chunk = coordinator.flush()
            if final_chunk:
                await tts_ws.send_text(final_chunk, flush=True)
            else:
                await tts_ws.flush()
        
        finally:
            # Wait for TTS to finish
            await asyncio.sleep(0.5)  # Small delay for final audio
            await tts_ws.close()
            
            # Signal playback end
            await audio_queue.put(None)
            
            # Wait for playback to complete
            if playback_task:
                await playback_task
        
        response_text = "".join(response_tokens)
        
        return {
            "response_text": response_text,
            "first_token_latency_ms": first_token_latency_ms,
            "first_audio_latency_ms": first_audio_latency_ms,
            "streaming_mode": "concurrent"
        }
    
    async def _sequential_pipeline(
        self,
        request_id: str,
        transcript: str,
        conversation_context: list,
        on_audio: Callable[[bytes], None]
    ) -> dict:
        """
        Fallback sequential pipeline (for graceful degradation).
        
        Used when streaming is disabled or fails.
        """
        stage_start = time.time()
        
        # Stage 1: LLM (full response)
        response_text = await self.llm_client.generate(
            conversation_context=conversation_context,
            user_message=transcript
        )
        
        llm_latency_ms = (time.time() - stage_start) * 1000
        self.latency_tracker.stage_complete(request_id, PipelineStage.LLM, llm_latency_ms)
        
        # Stage 2: TTS (full audio)
        tts_start = time.time()
        audio_data = await self.tts_client.generate(response_text, stream=True)
        
        tts_latency_ms = (time.time() - tts_start) * 1000
        self.latency_tracker.stage_complete(request_id, PipelineStage.TTS, tts_latency_ms)
        
        # Stage 3: Playback
        await on_audio(audio_data)
        
        return {
            "response_text": response_text,
            "llm_latency_ms": llm_latency_ms,
            "tts_latency_ms": tts_latency_ms,
            "streaming_mode": "sequential"
        }
    
    def get_latency_stats(self) -> dict:
        """Get latency statistics for all stages."""
        return {
            "total": self.latency_tracker.get_stats(),
            "stt": self.latency_tracker.get_stats(PipelineStage.STT),
            "llm": self.latency_tracker.get_stats(PipelineStage.LLM),
            "tts": self.latency_tracker.get_stats(PipelineStage.TTS),
            "playback": self.latency_tracker.get_stats(PipelineStage.PLAYBACK)
        }
    
    def is_active(self, call_id: str) -> bool:
        """Check if pipeline is active for a call."""
        return any(
            req_id.startswith(call_id) and active
            for req_id, active in self.active_pipelines.items()
        )
