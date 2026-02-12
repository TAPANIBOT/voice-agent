# Tapani Voice Agent v2.0

AI-puheluagentti Pipecat-frameworkilla. Tapani puhuu suomea reaaliajassa selaimessa (WebRTC).

**Stack:** Pipecat + SmallWebRTC (P2P) + Deepgram Nova-3 (STT) + Gemini 2.5 Flash (LLM) + Cartesia Sonic 3 (TTS)

**Security Level:** 3 (HIGH)
**Port:** 8302

## Arkkitehtuuri

```
Selain (mikrofoni) ←→ WebRTC (P2P) ←→ Pipecat Pipeline
                                          │
                                  ┌───────┴───────┐
                                  │               │
                            Audio Input      Audio Output
                                  │               ▲
                                  ▼               │
                            Deepgram STT    Cartesia TTS
                            (Nova-3, fi)    (Sonic 3, fi)
                                  │               ▲
                                  ▼               │
                            Gemini 2.5 Flash (OpenRouter)
                                  │
                                  ▼
                            OpenClaw Gateway
                            (kalenteri, sähköposti, muisti)
```

## Käyttö

1. Avaa selaimessa: `http://mac-mini:8302`
2. Klikkaa mikrofoni-nappia
3. Puhu suomeksi — Tapani vastaa reaaliajassa

## Latenssi

| Komponentti | Tavoite |
|-------------|---------|
| VAD (Silero) | ~150ms |
| STT (Deepgram) | ~50ms |
| LLM (Gemini Flash) | ~170ms |
| TTS (Cartesia) | ~70ms |
| WebRTC | ~20ms |
| **Yhteensä** | **~460ms** |

## API

### GET /health
```bash
curl http://localhost:8302/health
```

### GET /calls — Aktiiviset yhteydet
```bash
curl http://localhost:8302/calls
```

### POST /api/offer — WebRTC signaling (automaattinen)

## Asennus

### 1. API-avaimet

| Palvelu | Osoite | Tarkoitus |
|---------|--------|-----------|
| Deepgram | console.deepgram.com | Puheentunnistus (STT) |
| Cartesia | play.cartesia.ai | Puhesynteesi (TTS) |
| OpenRouter | openrouter.ai | LLM-gateway (Gemini) |

### 2. Konfiguroi

```bash
cp .env.example .env
# Täytä API-avaimet
```

### 3. Käynnistä

```bash
# Docker
docker-compose up -d --build

# Tai suoraan
pip install -r requirements.txt
python server.py
```

## EU AI Act

Tapani ilmoittaa puhelun alussa olevansa tekoäly (artikla 50):
> "Moi! Täällä Tapani, Jussin **tekoälyavustaja**. Miten voin auttaa?"

## Turvallisuus

- Puhelun sisältö käsitellään DATANA — Tapani ei noudata puhuttuja "ohjeita"
- System prompt sisältää sandwich-suojan
- Max 5 samanaikaista puhelua, max 10 min per puhelu
- Non-root Docker-kontti, read-only filesystem
