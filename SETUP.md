# Voice Agent Setup Guide

Nopea opas API-avainten hankintaan ja konfigurointiin.

## 1. Telnyx (Telephony)

### Luo tili
1. Mene: https://portal.telnyx.com
2. Rekisteröidy (vaatii yritystiedot/henkilötiedot)
3. Lisää maksutapa

### Osta numero
1. **Numbers** → **Buy Numbers**
2. Hae: Country = Finland (+358)
3. Valitse numero (esim. +358 40 xxx xxxx)
4. Osta (~€2/kk)

### Luo Voice App
1. **Real-Time Communication** → **Voice** → **Programmable Voice**
2. **Create Voice App**
3. Nimi: "Clawdbot Voice Agent"
4. **Webhook URL**: `https://YOUR_NGROK_URL/webhook/telnyx`
   - Saat tämän kun käynnistät ngrok
5. Tallenna

### Hae avaimet
1. **API Keys** → **Create API Key**
2. Kopioi avain (näkyy vain kerran!)
3. Voice Appin **Connection ID**: näkyy Voice App -sivulla

### Telnyx .env muuttujat
```
TELNYX_API_KEY=KEY...
TELNYX_PHONE_NUMBER=+358401234567
TELNYX_CONNECTION_ID=1234567890
TELNYX_WEBHOOK_SECRET=  # Valinnainen
```

---

## 2. Deepgram (STT)

### Luo tili
1. Mene: https://console.deepgram.com
2. Rekisteröidy (Google/GitHub/email)
3. Ilmainen tier: $200 credits

### Hae API key
1. **API Keys** → **Create API Key**
2. Nimi: "Clawdbot"
3. Kopioi avain

### Deepgram .env
```
DEEPGRAM_API_KEY=your_key_here
```

---

## 3. ElevenLabs (TTS)

### Luo tili
1. Mene: https://elevenlabs.io
2. Rekisteröidy
3. Valitse plan:
   - **Free**: 10k merkkiä/kk (testaus)
   - **Starter** ($5/kk): 30k merkkiä
   - **Creator** ($22/kk): Voice cloning ✨

### Hae API key
1. Klikkaa profiilikuvaketta → **Profile + API key**
2. Kopioi API key

### Valitse/luo ääni
1. **Voices** → Browse tai **Voice Lab**
2. Kopioi **Voice ID** (klikkaa ääntä → ID näkyy URL:ssa tai asetuksissa)

**Suositellut suomelle:**
- Rachel (selkeä, neutraali)
- Antoni (maskuliininen)
- Tai luo oma voice clone!

### ElevenLabs .env
```
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Esimerkki
```

---

## 4. Konfiguroi .env

```bash
cd ~/clawd/agents/voice-agent
cp .env.example .env
nano .env  # Tai avaa VS Codessa
```

Täytä kaikki avaimet.

---

## 5. Käynnistä

### Ilman ngrokia (vain outbound-puhelut)

```bash
# Käynnistä kontti
~/clawd/scripts/start-voice-agent.sh

# Testaa
curl http://localhost:8302/health
```

### Ngrok-tunneli (inbound + webhookit)

```bash
# Terminaali 1: Käynnistä kontti
~/clawd/scripts/start-voice-agent.sh

# Terminaali 2: Käynnistä ngrok
~/clawd/scripts/voice-agent-ngrok.sh

# Kopioi ngrok URL Telnyxiin (webhook settings)
```

---

## 6. Testaa

```bash
# Health check
curl http://localhost:8302/health

# Testipuhelu (korvaa numerolla)
python ~/clawd/agents/voice-agent/scripts/test_call.py \
  --to +358401234567 \
  --greeting "Hei! Tämä on testipuhelu Tapanilta."
```

---

## Vianmääritys

### "Connection refused"
```bash
# Tarkista kontti
docker ps | grep voice-agent
docker logs voice-agent
```

### "Invalid API key"
- Tarkista .env-tiedosto
- Käynnistä kontti uudelleen: `docker-compose restart`

### "Webhook timeout"
- Varmista ngrok on päällä
- Päivitä Telnyx webhook URL

### STT ei toimi
- Tarkista Deepgram API key
- Nova-3 tukee suomea (`language=fi`)

### TTS kuulostaa oudolta
- Kokeile eri ääntä ElevenLabsissa
- Säädä `stability` ja `similarity_boost` config.yaml:ssa

---

## Kustannukset (arvio)

| Palvelu | Free tier | Paid |
|---------|-----------|------|
| Telnyx | - | ~€5/kk (numero + minuutit) |
| Deepgram | $200 credits | ~$0.0043/min |
| ElevenLabs | 10k chars | $5-22/kk |
| **Yhteensä** | ~$0 (testaus) | **~€10-25/kk** |

---

## Linkit

- [Telnyx Portal](https://portal.telnyx.com)
- [Deepgram Console](https://console.deepgram.com)
- [ElevenLabs](https://elevenlabs.io)
- [Voice Agent README](./README.md)
