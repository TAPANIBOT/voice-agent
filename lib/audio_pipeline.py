import asyncio
import time
from typing import Dict, Optional

from lib.deepgram_client import DeepgramSTT
from lib.elevenlabs_client import ElevenLabsTTS
from lib.claude_client import ClaudeStreaming
from lib.conversation import ConversationManager
from lib.humanlike import HumanlikeBehavior


class AudioPipeline:
    def __init__(self):
        self.pipelines: Dict[str, 'PipelineInstance'] = {}
        self.stats: Dict[str, Dict[str, float]] = {}

    async def start_pipeline(self, call_id: str, audio_stream):
        """Start the audio processing pipeline for a call."""
        if call_id in self.pipelines:
            raise ValueError(f"Pipeline for call_id {call_id} already exists")

        pipeline = PipelineInstance(call_id, audio_stream)
        self.pipelines[call_id] = pipeline
        self.stats[call_id] = {
            'total_latency': 0.0,
            'stt_latency': 0.0,
            'llm_latency': 0.0,
            'tts_latency': 0.0,
            'count': 0
        }

        await pipeline.start()
        return f"Pipeline started for call_id: {call_id}"

    async def stop_pipeline(self, call_id: str):
        """Stop the audio processing pipeline for a call."""
        if call_id not in self.pipelines:
            raise ValueError(f"No pipeline found for call_id {call_id}")

        pipeline = self.pipelines[call_id]
        await pipeline.stop()
        del self.pipelines[call_id]
        del self.stats[call_id]
        return f"Pipeline stopped for call_id: {call_id}"

    async def inject_filler_word(self, call_id: str, word: str):
        """Inject a filler word into the pipeline."""
        if call_id not in self.pipelines:
            raise ValueError(f"No pipeline found for call_id {call_id}")

        pipeline = self.pipelines[call_id]
        await pipeline.inject_filler_word(word)
        return f"Filler word '{word}' injected into call_id: {call_id}"

    def get_pipeline_stats(self, call_id: str) -> Optional[Dict[str, float]]:
        """Get latency statistics for a pipeline."""
        if call_id not in self.stats:
            return None

        stats = self.stats[call_id]
        if stats['count'] == 0:
            return None

        avg_latency = stats['total_latency'] / stats['count']
        return {
            'average_total_latency': avg_latency,
            'average_stt_latency': stats['stt_latency'] / stats['count'],
            'average_llm_latency': stats['llm_latency'] / stats['count'],
            'average_tts_latency': stats['tts_latency'] / stats['count'],
            'count': stats['count']
        }


class PipelineInstance:
    def __init__(self, call_id: str, audio_stream):
        self.call_id = call_id
        self.audio_stream = audio_stream
        self.running = False
        self.stt_client = DeepgramSTT()
        self.tts_client = ElevenLabsTTS()
        self.llm_client = ClaudeStreaming()
        self.conversation = ConversationManager()
        self.humanlike = HumanlikeBehavior()
        self.filler_queue = asyncio.Queue()

    async def start(self):
        """Start all processing tasks concurrently."""
        self.running = True
        await asyncio.gather(
            self._process_audio(),
            self._process_filler_words(),
            self._monitor_pipeline()
        )

    async def stop(self):
        """Stop all processing tasks."""
        self.running = False

    async def inject_filler_word(self, word: str):
        """Inject a filler word into the processing queue."""
        await self.filler_queue.put(word)

    async def _process_audio(self):
        """Main audio processing loop."""
        while self.running:
            try:
                # Get audio chunk from stream
                audio_chunk = await self.audio_stream.get_chunk()
                if not audio_chunk:
                    continue

                # Process through pipeline
                start_time = time.time()

                # 1. STT processing
                stt_start = time.time()
                stt_result = await self.stt_client.transcribe(audio_chunk)
                stt_latency = time.time() - stt_start

                # 2. LLM processing
                llm_start = time.time()
                llm_response = await self.llm_client.generate_response(stt_result)
                llm_latency = time.time() - llm_start

                # 3. TTS processing
                tts_start = time.time()
                tts_audio = await self.tts_client.synthesize(llm_response)
                tts_latency = time.time() - tts_start

                # 4. Humanlike behavior adjustments
                final_audio = self.humanlike.adjust_audio(tts_audio)

                # 5. Send to Telnyx
                await self._send_to_telnyx(final_audio)

                # Update statistics
                total_latency = time.time() - start_time
                self._update_stats(total_latency, stt_latency, llm_latency, tts_latency)

            except Exception as e:
                print(f"Error in audio processing: {e}")

    async def _process_filler_words(self):
        """Process filler words from the queue."""
        while self.running:
            try:
                word = await self.filler_queue.get()
                if not word:
                    continue

                # Generate TTS for filler word
                tts_audio = await self.tts_client.synthesize(word)
                final_audio = self.humanlike.adjust_audio(tts_audio)

                # Send to Telnyx
                await self._send_to_telnyx(final_audio)

            except Exception as e:
                print(f"Error processing filler word: {e}")

    async def _monitor_pipeline(self):
        """Monitor pipeline health and performance."""
        while self.running:
            await asyncio.sleep(10)
            # Add monitoring logic here

    async def _send_to_telnyx(self, audio_data):
        """Send audio to Telnyx media stream."""
        # Implementation would depend on Telnyx SDK
        pass

    def _update_stats(self, total_latency, stt_latency, llm_latency, tts_latency):
        """Update pipeline statistics."""
        pipeline_manager = AudioPipeline()
        if self.call_id in pipeline_manager.stats:
            stats = pipeline_manager.stats[self.call_id]
            stats['total_latency'] += total_latency
            stats['stt_latency'] += stt_latency
            stats['llm_latency'] += llm_latency
            stats['tts_latency'] += tts_latency
            stats['count'] += 1