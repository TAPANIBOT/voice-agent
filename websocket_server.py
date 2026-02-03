            "intent": intent,
            "sentiment": sentiment,
            "context": {
                "turn_count": self.conversation.get_conversation(self.call_id).get_turn_count() if self.conversation.get_conversation(self.call_id) else 0,
                "topics": self.conversation.get_conversation(self.call_id).get_topics() if self.conversation.get_conversation(self.call_id) else []
            },
            "_security_notice": SECURITY_NOTICE
        })

    async def _on_speech_started(self):
        """Called when user starts speaking."""
        self.user_speaking = True
        
        # If agent is speaking, handle barge-in
        if self.is_speaking and self.config.get("turn_taking", {}).get("barge_in_enabled", True):
            logger.info("media_stream_handler.barge_in", call_id=self.call_id)
            await self._stop_speaking()

    async def _on_speech_ended(self):
        """Called when user stops speaking."""
        self.user_speaking = False

    async def speak(self, text: str):
        """
        Generate TTS and play on call.
        
        Args:
            text: Text to speak
        """
        if not self.active:
            return
            
        self.is_speaking = True
        
        try:
            logger.info("media_stream_handler.speaking",
                       call_id=self.call_id,
                       text_length=len(text))
            
            # Generate TTS
            async for chunk in self.elevenlabs.synthesize_stream(text):
                # Process outbound audio
                await self.process_outbound_audio(chunk.audio)
                
                # Add to conversation
                self.conversation.add_turn(self.call_id, "assistant", text)
                
        except Exception as e:
            logger.error("media_stream_handler.speak_error",
                        call_id=self.call_id,
                        error=str(e))
        finally:
            self.is_speaking = False

    async def _stop_speaking(self):
        """Stop current TTS playback (for barge-in)."""
        # Send clear message to Telnyx
        await self.telnyx_ws.send(json.dumps({"event": "clear"}))
        self.is_speaking = False

    async def stop(self):
        """Stop the media streaming session."""
        self.active = False
        
        # Stop audio pipeline
        await self.audio_pipeline.stop_pipeline(self.call_id)
        
        logger.info("media_stream_handler.stopped", call_id=self.call_id)


class MediaStreamServer:
    """
    WebSocket server for handling Telnyx media streams.
    """
    
    def __init__(
        self,
        deepgram: DeepgramSTT,
        elevenlabs: ElevenLabsTTS,
        conversation: ConversationManager,
        callback_url: str,
        config: dict,
        host: str = "0.0.0.0",
        port: int = 8081
    ):
        self.deepgram = deepgram
        self.elevenlabs = elevenlabs
        self.conversation = conversation
        self.callback_url = callback_url
        self.config = config
        self.host = host
        self.port = port
        
        self.sessions: Dict[str, MediaStreamHandler] = {}

    async def start(self):
        """Start the WebSocket server."""
        logger.info("media_server.starting", host=self.host, port=self.port)
        
        async with websockets.serve(
            self._handle_connection,
            self.host,
            self.port
        ):
            logger.info("media_server.running")
            await asyncio.Future()  # Run forever

    async def _handle_connection(
        self,
        websocket: websockets.WebSocketServerProtocol,
        path: str
    ):
        """Handle incoming WebSocket connection from Telnyx."""
        call_id = None
        
        try:
            # Wait for start message to get call_id
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("event") != "connected":
                logger.warning("media_server.unexpected_first_message")
                return
            
            # Wait for start message with call details
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("event") != "start":
                logger.warning("media_server.no_start_message")
                return
            
            call_id = data.get("start", {}).get("call_control_id")
            if not call_id:
                logger.warning("media_server.no_call_id")
                return
            
            logger.info("media_server.connection_started", call_id=call_id)
            
            # Create handler
            handler = MediaStreamHandler(
                call_id=call_id,
                telnyx_ws=websocket,
                deepgram=self.deepgram,
                elevenlabs=self.elevenlabs,
                conversation=self.conversation,
                on_transcript=self._send_to_callback,
                config=self.config.get("voice", {})
            )
            
            self.sessions[call_id] = handler
            
            # Start handling connection
            await handler.handle_connection(websocket, call_id)
            
        except websockets.ConnectionClosed:
            logger.info("media_server.connection_closed", call_id=call_id)
        except Exception as e:
            logger.error("media_server.error", call_id=call_id, error=str(e))
        finally:
            if call_id and call_id in self.sessions:
                await self.sessions[call_id].stop()
                del self.sessions[call_id]

    async def _send_to_callback(self, transcript: str, metadata: dict):
        """Send transcript to Clawdbot callback URL."""
        if not self.callback_url:
            logger.warning("media_server.no_callback_url")
            return
        
        payload = {
            "event": "transcript",
            "transcript": transcript,
            **metadata
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.callback_url,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    # Check if response contains text to speak
                    data = response.json()
                    if "response" in data:
                        call_id = metadata.get("call_id")
                        if call_id in self.sessions:
                            await self.sessions[call_id].speak(data["response"])
                
        except Exception as e:
            logger.error("media_server.callback_error", error=str(e))

    async def speak_on_call(self, call_id: str, text: str):
        """
        Speak text on a specific call.
        
        Args:
            call_id: Call identifier
            text: Text to speak
        """
        session = self.sessions.get(call_id)
        if session:
            await session.speak(text)
        else:
            logger.warning("media_server.session_not_found", call_id=call_id)


# Entry point for standalone WebSocket server
if __name__ == "__main__":
    import yaml
    
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Initialize clients
    deepgram = DeepgramSTT(
        api_key=os.environ['DEEPGRAM_API_KEY'],
        language=config['voice']['stt'].get('language', 'fi'),
        model=config['voice']['stt'].get('model', 'nova-3')
    )
    
    elevenlabs = ElevenLabsTTS(
        api_key=os.environ['ELEVENLABS_API_KEY'],
        voice_id=os.environ['ELEVENLABS_VOICE_ID'],
        model=config['voice']['tts'].get('model', 'eleven_flash_v2_5')
    )
    
    conversation = ConversationManager(config['conversation'])
    
    # Create server
    server = MediaStreamServer(
        deepgram=deepgram,
        elevenlabs=elevenlabs,
        conversation=conversation,
        callback_url=os.environ.get('CALLBACK_URL', ''),
        config=config,
        port=int(os.environ.get('WS_PORT', 8081))
    )
    
    # Run
    asyncio.run(server.start())