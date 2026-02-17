"""Text-to-Speech service using ElevenLabs free tier API."""

import io
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ElevenLabs free voices (available without subscription)
ELEVENLABS_VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",       # Female, calm, narration
    "drew": "29vD33N1CtxCmqQRPOHJ",          # Male, well-rounded
    "clyde": "2EiwWnXFnvU5JabPnv8n",         # Male, war veteran character
    "paul": "5Q0t7uMcjvnagumLfvZi",          # Male, ground reporter
    "domi": "AZnzlk1XvdvUeBnXmlld",          # Female, strong
    "dave": "CYw3kZ02Hs0563khs1Fj",          # Male, conversational
    "fin": "D38z5RcWu1voky8WS1ja",           # Male, sailor character
    "sarah": "EXAVITQu4vr4xnSDxMaL",         # Female, soft news
    "antoni": "ErXwobaYiN019PkySvjV",        # Male, well-rounded
    "thomas": "GBv7mTt0atIp3Br8iCZE",        # Male, calm
    "charlie": "IKne3meq5aSn9XLyUdCD",       # Male, casual Australian
    "emily": "LcfcDJNUP1GQjkzn1xUU",         # Female, calm
    "elli": "MF3mGyEYCl7XYWbV9V6O",          # Female, emotional
    "callum": "N2lVS1w4EtoT3dr4eOWO",        # Male, hoarse
    "patrick": "ODq5zmih8GrVes37Dizd",        # Male, shouty
    "harry": "SOYHLrjzK2X1ezoPC6cr",         # Male, anxious
    "liam": "TX3LPaxmHKxFdv7VOQHJ",          # Male, articulate
    "dorothy": "ThT5KcBeYPX3keUQqHPh",       # Female, pleasant
    "josh": "TxGEqnHWrfWFTfGW9XjX",          # Male, deep
    "arnold": "VR6AewLTigWG4xSOukaG",        # Male, crisp
    "charlotte": "XB0fDUnXU5powFXDhCwa",     # Female, seductive
    "matilda": "XrExE9yKIg1WjnnlVkGX",       # Female, warm
    "matthew": "Yko7PKHZNXotIFUBG7I9",       # Male, audiobook
    "james": "ZQe5CZNOzWyzPSCn5a3c",         # Male, authoritative
    "joseph": "Zlb1dXrM653N07WRdFW3",        # Male, articulate
    "jeremy": "bVMeCyTHy58xNoL34h3p",        # Male, excited
    "michael": "flq6f7yk4E4fJM5XTYuZ",       # Male, old
    "ethan": "g5CIjZEefAph4nQFvHAz",         # Male, soft
    "george": "JBFqnCBsd6RMkjVDRZzb",        # Male, warm British
    "chris": "iP95p4xoKVk53GoZ742B",         # Male, casual
    "gigi": "jBpfuIE2acCO8z3wKNLl",          # Female, childish
    "freya": "jsCqWAovK2LkecY7zXl4",         # Female, overhyped
    "brian": "nPczCjzI2devNBz1zQrb",          # Male, deep
    "grace": "oWAxZDx7w5VEj9dCyTzz",         # Female, southern accent
    "daniel": "onwK4e9ZLuTAKqWW03F9",        # Male, deep, authoritative
    "lily": "pFZP5JQG7iQjIQuC4Bku",          # Female, warm British
    "serena": "pMsXgVXv3BLzUgSXRplE",        # Female, pleasant
    "adam": "pNInz6obpgDQGcFmaJgB",          # Male, deep
    "nicole": "piTKgcLEGmPE4e6mEKli",        # Female, whisper
    "bill": "pqHfZKP75CvOlQylNhV4",          # Male, strong
    "jessie": "t0jbNlBVZ17f02VDIeMI",        # Female, fast
    "sam": "yoZ06aMxZJJ28mfd3POQ",           # Male, raspy
    "glinda": "z9fAnlkpzviPz146aGWa",        # Female, witch
    "giovanni": "zcAOhNBS3c14rBihAFp1",      # Male, Italian accent
    "mimi": "zrHiDhphv9ZnVXBqCLjz",          # Female, childish
}

# Default voice for the bot
DEFAULT_VOICE = "rachel"

# ElevenLabs API base
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


class TTSService:
    """ElevenLabs Text-to-Speech service."""

    def __init__(self, api_key: str, voice_id: str | None = None,
                 model_id: str = "eleven_multilingual_v2") -> None:
        self.api_key = api_key
        self.voice_id = voice_id or ELEVENLABS_VOICES.get(DEFAULT_VOICE, "")
        self.model_id = model_id
        self._enabled = bool(api_key)

        if self._enabled:
            logger.info("ElevenLabs TTS initialised (voice=%s, model=%s)",
                        self._voice_name(), model_id)
        else:
            logger.warning("ElevenLabs TTS disabled — no API key configured. "
                           "Set ELEVENLABS_API_KEY in .env to enable.")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _voice_name(self) -> str:
        """Resolve voice ID back to a name for logging."""
        for name, vid in ELEVENLABS_VOICES.items():
            if vid == self.voice_id:
                return name
        return self.voice_id[:8]

    def synthesize(self, text: str, voice_id: str | None = None) -> Optional[bytes]:
        """Convert text to speech audio (MP3 bytes).

        Args:
            text: The text to convert to speech.
            voice_id: Override voice (name or ID). Falls back to default.

        Returns:
            MP3 audio bytes, or None on failure.
        """
        if not self._enabled:
            logger.warning("TTS is disabled — missing API key")
            return None

        if not text or not text.strip():
            return None

        # Resolve voice name to ID if needed
        resolved_voice = voice_id or self.voice_id
        if resolved_voice in ELEVENLABS_VOICES:
            resolved_voice = ELEVENLABS_VOICES[resolved_voice]

        # Truncate very long text to stay within free tier limits
        max_chars = 2500
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
            logger.info("TTS text truncated to %d chars", max_chars)

        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{resolved_voice}"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code == 200:
                audio_bytes = resp.content
                logger.info("TTS synthesised %d bytes of audio for %d chars of text",
                            len(audio_bytes), len(text))
                return audio_bytes

            # Handle common errors
            if resp.status_code == 401:
                logger.error("ElevenLabs API key is invalid or expired")
            elif resp.status_code == 429:
                logger.warning("ElevenLabs rate limit / quota exceeded")
            else:
                logger.error("ElevenLabs TTS error %d: %s",
                             resp.status_code, resp.text[:200])
            return None

        except requests.exceptions.Timeout:
            logger.error("ElevenLabs TTS request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error("ElevenLabs TTS request failed: %s", e)
            return None

    def list_voices(self) -> dict:
        """Return the available built-in voices."""
        return {name: vid for name, vid in ELEVENLABS_VOICES.items()}

    def get_usage(self) -> Optional[dict]:
        """Fetch current API usage / quota info from ElevenLabs."""
        if not self._enabled:
            return None
        try:
            resp = requests.get(
                f"{ELEVENLABS_API_BASE}/user/subscription",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "character_count": data.get("character_count", 0),
                    "character_limit": data.get("character_limit", 0),
                    "tier": data.get("tier", "free"),
                }
        except Exception as e:
            logger.warning("Failed to fetch ElevenLabs usage: %s", e)
        return None
