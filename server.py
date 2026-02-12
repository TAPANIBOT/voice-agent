"""Tapani Voice Agent — WebRTC + PSTN server.

Handles:
- WebRTC browser calls (SmallWebRTCTransport)
- Telnyx PSTN calls (webhook + WebSocket)
- Health checks
"""

import argparse
import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict

import httpx
import telnyx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pipecat.runner.utils import parse_telephony_websocket

from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler

from bot import run_telnyx_pipeline, run_voice_pipeline
from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Track active PSTN calls
active_calls: dict[str, dict] = {}

# ICE servers — updated dynamically with TURN credentials
_ice_servers_cache: list[IceServer] = []
_ice_servers_lock = asyncio.Lock()
_ice_servers_last_refresh: float = 0
_ICE_REFRESH_INTERVAL = 3600  # 1 hour


async def _fetch_ice_servers() -> list[IceServer]:
    """Fetch TURN credentials from Metered.ca API, with STUN fallback."""
    servers = [IceServer(urls="stun:stun.l.google.com:19302")]

    if not config.turn_api_key:
        logger.info("No TURN_API_KEY — STUN only mode")
        return servers

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                config.turn_api_url,
                params={"apiKey": config.turn_api_key},
            )
            resp.raise_for_status()
            for srv in resp.json():
                servers.append(IceServer(
                    urls=srv["urls"],
                    username=srv.get("username", ""),
                    credential=srv.get("credential", ""),
                ))
        logger.info(f"Fetched {len(servers) - 1} TURN server(s) from Metered.ca")
    except Exception as e:
        logger.error(f"Failed to fetch TURN credentials: {e}")

    return servers


async def _get_ice_servers() -> list[IceServer]:
    """Return cached ICE servers, refreshing if stale (>1h)."""
    global _ice_servers_cache, _ice_servers_last_refresh

    now = time.time()
    if _ice_servers_cache and (now - _ice_servers_last_refresh) < _ICE_REFRESH_INTERVAL:
        return _ice_servers_cache

    async with _ice_servers_lock:
        # Double-check after acquiring lock
        if _ice_servers_cache and (time.time() - _ice_servers_last_refresh) < _ICE_REFRESH_INTERVAL:
            return _ice_servers_cache
        _ice_servers_cache = await _fetch_ice_servers()
        _ice_servers_last_refresh = time.time()
        return _ice_servers_cache


# Initialize with STUN-only; TURN credentials loaded at startup
ice_servers = [IceServer(urls="stun:stun.l.google.com:19302")]
webrtc_handler = SmallWebRTCRequestHandler(ice_servers=ice_servers)


async def _ice_refresh_loop():
    """Periodically refresh TURN credentials in background."""
    while True:
        await asyncio.sleep(_ICE_REFRESH_INTERVAL)
        try:
            servers = await _fetch_ice_servers()
            global _ice_servers_cache, _ice_servers_last_refresh
            _ice_servers_cache = servers
            _ice_servers_last_refresh = time.time()
            webrtc_handler.update_ice_servers(servers)
            logger.info("ICE servers refreshed")
        except Exception as e:
            logger.error(f"ICE refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    missing = config.validate()
    if missing:
        logger.warning(f"Missing config: {', '.join(missing)}")
    else:
        logger.info("All config values present")

    # Fetch TURN credentials and update handler
    servers = await _get_ice_servers()
    webrtc_handler.update_ice_servers(servers)

    # Start background TURN credential refresh
    refresh_task = asyncio.create_task(_ice_refresh_loop())

    if config.telnyx_api_key:
        telnyx.api_key = config.telnyx_api_key
        logger.info("Telnyx PSTN enabled")
    else:
        logger.info("Telnyx PSTN disabled (no API key)")

    logger.info(f"Voice Agent starting on {config.host}:{config.port}")
    yield
    refresh_task.cancel()
    active_calls.clear()
    logger.info("Voice Agent shut down")


app = FastAPI(title="Tapani Voice Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tapani---mac-mini.tail3d5d3c.ts.net:8302",
        "https://localhost:8302",
        "http://localhost:8302",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root_redirect():
    """Redirect root to the custom WebRTC client UI."""
    return RedirectResponse(url="/static/index.html")


@app.post("/start")
async def start():
    """Return WebRTC offer URL and ICE servers (including TURN)."""
    servers = await _get_ice_servers()
    return {
        "webrtcUrl": "/api/offer",
        "iceServers": [
            {
                "urls": s.urls,
                **({"username": s.username} if s.username else {}),
                **({"credential": s.credential} if s.credential else {}),
            }
            for s in servers
        ],
    }


@app.post("/api/offer")
async def offer(request: Request, background_tasks: BackgroundTasks):
    """WebRTC SDP offer/answer exchange."""
    body = await request.json()

    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    webrtc_request = SmallWebRTCRequest(
        sdp=body["sdp"],
        type=body["type"],
        pc_id=body.get("pc_id"),
        restart_pc=body.get("restart_pc", False),
    )

    async def on_connection(connection: SmallWebRTCConnection):
        background_tasks.add_task(run_voice_pipeline, connection)
        logger.info("New WebRTC connection, starting pipeline")

    answer = await webrtc_handler.handle_web_request(
        request=webrtc_request,
        webrtc_connection_callback=on_connection,
    )
    return answer


@app.patch("/api/offer")
async def ice_candidate(request: Request):
    """WebRTC ICE candidate trickle."""
    body = await request.json()

    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCPatchRequest, IceCandidate
    patch_request = SmallWebRTCPatchRequest(
        pc_id=body["pc_id"],
        candidates=[IceCandidate(**c) for c in body.get("candidates", [])],
    )
    answer = await webrtc_handler.handle_patch_request(patch_request)
    return answer


@app.get("/health")
async def health():
    """Health check."""
    missing = config.validate()
    return {
        "status": "ok" if not missing else "degraded",
        "active_webrtc": len(webrtc_handler._pcs_map),
        "active_pstn": len(active_calls),
        "missing_config": missing,
    }


@app.get("/calls")
async def list_calls():
    """List active WebRTC and PSTN connections."""
    pstn_calls = []
    for cc_id, info in active_calls.items():
        pstn_calls.append({
            "call_id": info["call_id"],
            "direction": info["direction"],
            "from": info["from"],
            "to": info["to"],
            "status": info["status"],
            "duration": int(time.time() - info["started_at"]),
        })
    return {
        "webrtc_connections": list(webrtc_handler._pcs_map.keys()),
        "pstn_calls": pstn_calls,
        "total": len(webrtc_handler._pcs_map) + len(active_calls),
    }


# ============================================================
# Telnyx PSTN endpoints
# ============================================================


@app.post("/webhook/telnyx")
async def telnyx_webhook(request: Request):
    """Handle Telnyx call events."""
    body = await request.json()
    data = body.get("data", {})
    event_type = data.get("event_type", "")
    payload = data.get("payload", {})

    logger.info(f"Telnyx webhook: {event_type}")

    if event_type == "call.initiated":
        direction = payload.get("direction", "")
        call_control_id = payload.get("call_control_id", "")
        from_number = payload.get("from", "")
        to_number = payload.get("to", "")

        if direction == "incoming":
            logger.info(f"Incoming call from {from_number} to {to_number}")

            total_active = len(webrtc_handler._pcs_map) + len(active_calls)
            if total_active >= config.max_concurrent_calls:
                logger.warning("Max concurrent calls reached, rejecting")
                try:
                    call = telnyx.Call.create(call_control_id=call_control_id)
                    call.reject(cause="USER_BUSY")
                except Exception as e:
                    logger.error(f"Failed to reject call: {e}")
                return JSONResponse({"status": "rejected"})

            try:
                call = telnyx.Call.create(call_control_id=call_control_id)
                call.answer()
            except Exception as e:
                logger.error(f"Failed to answer call: {e}")
                return JSONResponse({"status": "error"}, status_code=500)

            call_id = str(uuid.uuid4())[:8]
            active_calls[call_control_id] = {
                "call_id": call_id,
                "direction": "inbound",
                "from": from_number,
                "to": to_number,
                "call_control_id": call_control_id,
                "started_at": time.time(),
                "status": "answered",
            }

    elif event_type == "call.answered":
        call_control_id = payload.get("call_control_id", "")
        logger.info(f"Call answered: {call_control_id}")

        try:
            call = telnyx.Call.create(call_control_id=call_control_id)
            call.streaming_start(
                stream_url=config.ws_url,
                stream_track="both_tracks",
            )
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")

    elif event_type == "call.hangup":
        call_control_id = payload.get("call_control_id", "")
        hangup_cause = payload.get("hangup_cause", "unknown")
        logger.info(f"Call ended: {call_control_id}, cause: {hangup_cause}")

        if call_control_id in active_calls:
            call_info = active_calls.pop(call_control_id)
            duration = time.time() - call_info["started_at"]
            logger.info(
                f"Call {call_info['call_id']} ended after {duration:.0f}s "
                f"({call_info['from']} -> {call_info['to']})"
            )

    elif event_type == "streaming.started":
        logger.info("Media streaming started")

    return JSONResponse({"status": "ok"})


@app.websocket("/ws/telnyx")
async def telnyx_websocket(websocket: WebSocket):
    """WebSocket endpoint for Telnyx media streaming."""
    await websocket.accept()
    logger.info("Telnyx WebSocket connected")

    try:
        transport_type, call_data = await parse_telephony_websocket(websocket)

        if transport_type != "telnyx":
            logger.error(f"Unexpected transport type: {transport_type}")
            await websocket.close()
            return

        stream_id = call_data["stream_id"]
        call_control_id = call_data["call_control_id"]

        call_info = active_calls.get(call_control_id, {})
        direction = call_info.get("direction", "inbound")
        greeting = call_info.get("greeting")

        logger.info(
            f"Starting Telnyx pipeline: stream={stream_id}, "
            f"direction={direction}, call_control={call_control_id}"
        )

        await run_telnyx_pipeline(
            websocket=websocket,
            stream_id=stream_id,
            call_control_id=call_control_id,
            direction=direction,
            greeting=greeting,
        )

    except Exception as e:
        logger.error(f"Telnyx pipeline error: {e}", exc_info=True)
    finally:
        logger.info("Telnyx WebSocket disconnected")


async def _initiate_call(params: dict) -> dict:
    """Shared call initiation logic used by /call and /execute endpoints."""
    if not config.telnyx_api_key:
        raise HTTPException(status_code=503, detail="Telnyx not configured")

    to_number = params.get("to", "")
    greeting = params.get("greeting")
    context = params.get("context", "")

    if not to_number:
        raise HTTPException(status_code=400, detail="Missing 'to' number")
    if not any(to_number.startswith(p) for p in config.allowed_prefixes):
        raise HTTPException(status_code=403, detail="Number not in allowed prefixes")
    if any(to_number.startswith(p) for p in config.blocked_prefixes):
        raise HTTPException(status_code=403, detail="Number is blocked (premium)")

    total_active = len(webrtc_handler._pcs_map) + len(active_calls)
    if total_active >= config.max_concurrent_calls:
        raise HTTPException(status_code=429, detail="Max concurrent calls reached")

    try:
        call = telnyx.Call.create(
            connection_id=config.telnyx_connection_id,
            to=to_number,
            from_=config.telnyx_phone_number,
            webhook_url=f"{config.public_url}/webhook/telnyx",
            stream_url=config.ws_url,
            stream_track="both_tracks",
        )

        call_control_id = call.call_control_id
        call_id = str(uuid.uuid4())[:8]

        active_calls[call_control_id] = {
            "call_id": call_id,
            "direction": "outbound",
            "from": config.telnyx_phone_number,
            "to": to_number,
            "call_control_id": call_control_id,
            "started_at": time.time(),
            "status": "dialing",
            "greeting": greeting,
            "context": context,
        }

        logger.info(f"Outbound call initiated: {call_id} -> {to_number}")

        return {
            "success": True,
            "call_id": call_id,
            "call_control_id": call_control_id,
            "status": "dialing",
            "to": to_number,
        }

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/call")
async def initiate_call(request: Request):
    """Initiate an outbound PSTN call via Telnyx."""
    body = await request.json()
    return await _initiate_call(body)


@app.post("/hangup/{call_control_id}")
async def hangup_call(call_control_id: str):
    """Hang up an active PSTN call."""
    if call_control_id not in active_calls:
        raise HTTPException(status_code=404, detail="Call not found")

    try:
        call = telnyx.Call.create(call_control_id=call_control_id)
        call.hangup()
        return {"status": "hanging_up"}
    except Exception as e:
        logger.error(f"Failed to hangup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/execute")
async def execute(request: Request):
    """OpenClaw-compatible execute endpoint for PSTN calls."""
    body = await request.json()
    action = body.get("action", "")
    params = body.get("params", {})

    if action == "start_call":
        return await _initiate_call(params)
    elif action == "list_calls":
        return await list_calls()
    elif action == "hangup":
        cc_id = params.get("call_control_id", "")
        return await hangup_call(cc_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


# Mount custom frontend static files
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    logger.warning(f"Static directory not found: {_static_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tapani Voice Agent")
    parser.add_argument("--host", default=config.host)
    parser.add_argument("--port", type=int, default=config.port)
    args = parser.parse_args()

    ssl_kwargs = {}
    ssl_cert = os.environ.get("SSL_CERT_FILE")
    ssl_key = os.environ.get("SSL_KEY_FILE")
    if ssl_cert and ssl_key:
        ssl_kwargs = {"ssl_certfile": ssl_cert, "ssl_keyfile": ssl_key}
        logger.info(f"HTTPS enabled with {ssl_cert}")

    uvicorn.run(app, host=args.host, port=args.port, **ssl_kwargs)
