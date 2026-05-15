# =============================================================================
# backend/app/config.py
#
# PURPOSE: Central configuration hub for the entire backend.
#
# HOW IT WORKS:
#   - Reads environment variables from .env (via python-dotenv).
#   - Exposes a single `settings` object imported everywhere else.
#   - Swap STT providers by changing STT_PROVIDER here — nothing else changes.
#
# USAGE:
#   from app.config import settings
#   print(settings.GEMINI_API_KEY)
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "GD-Sim AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False                         # Enable only for local debugging

    # ── AI Brain: Gemini Flash ────────────────────────────────────────────────
    # Get free key at: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_KEYS: Optional[str] = None       # Array of comma separated keys for failover
    GEMINI_MODEL: str = "gemini-2.0-flash"      # Fast + free tier generous

    # ── Primary LLM Provider (for GD simulation) ────────────────────────────
    # "gemini" = Gemini first, Groq fallback
    # "groq"   = Groq first, Gemini fallback
    LLM_PRIMARY_PROVIDER: Literal["gemini", "groq"] = "gemini"

    # ── STT (Speech-to-Text) Provider ────────────────────────────────────────
    # "web_speech" = browser-native, zero cost, Chrome-only (good for MVP)
    # "groq"       = Groq Whisper, free 6K min/day, works on all browsers
    STT_PROVIDER: Literal["web_speech", "groq"] = "web_speech"

    # ── Groq STT (only needed if STT_PROVIDER = "groq") ──────────────────────
    # Get free key at: https://console.groq.com
    GROQ_API_KEY: str = ""
    GROQ_API_KEYS: str = ""                     # Array of comma separated keys
    GROQ_LLM_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TIMEOUT_MS: int = 12_000

    # ── Firebase Admin SDK ────────────────────────────────────────────────────
    # Download serviceAccountKey.json from Firebase Console → Project Settings
    # → Service Accounts → Generate New Private Key
    FIREBASE_SERVICE_ACCOUNT_PATH: str = "serviceAccountKey.json"
    FIREBASE_PROJECT_ID: str

    # ── ChromaDB Vector Store ─────────────────────────────────────────────────
    # File-based: no server needed. chroma_data/ folder is auto-created.
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_COLLECTION_NAME: str = "gd_topics"

    # ── GD Session Config ─────────────────────────────────────────────────────
    SILENCE_THRESHOLD_MS: int = 20_000         # Prod user if silent for 20s
    MAX_SESSION_TURNS: int = 40                # End GD after 40 turns
    AI_TURN_PAUSE_MIN: float = 0.4            # Human-like pause between AI turns (seconds)
    AI_TURN_PAUSE_MAX: float = 1.2

    # ── CORS (frontend URL) ───────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173" # Vite dev server
    # Comma-separated list of allowed origins for production (overrides FRONTEND_URL)
    ALLOWED_ORIGINS: str = ""

    # pydantic-settings reads from .env automatically
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    def get_gemini_keys(self) -> list[str]:
        keys = []
        if self.GEMINI_API_KEY:
            keys.extend([k.strip() for k in self.GEMINI_API_KEY.split(",") if k.strip()])
        if self.GEMINI_API_KEYS:
            keys.extend([k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()])
        return list(dict.fromkeys(keys)) # Remove duplicates

    def get_groq_keys(self) -> list[str]:
        keys = []
        if self.GROQ_API_KEY:
            keys.append(self.GROQ_API_KEY.strip())
        if self.GROQ_API_KEYS:
            keys.extend([k.strip() for k in self.GROQ_API_KEYS.split(",") if k.strip()])
        return list(dict.fromkeys(keys)) # Remove duplicates

    def get_allowed_origins(self) -> list[str]:
        """Return the list of allowed CORS origins.

        Production: set ALLOWED_ORIGINS=https://myapp.vercel.app,https://custom.domain
        Local dev:  leave empty — auto-expands FRONTEND_URL to include 127.0.0.1 variant.
        """
        if self.ALLOWED_ORIGINS:
            return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        return _build_allowed_origins(self.FRONTEND_URL)


def _build_allowed_origins(frontend_url: str) -> list[str]:
    origins = {frontend_url}
    if "localhost" in frontend_url:
        origins.add(frontend_url.replace("localhost", "127.0.0.1"))
    if "127.0.0.1" in frontend_url:
        origins.add(frontend_url.replace("127.0.0.1", "localhost"))
    return sorted(origins)


# Single instance imported everywhere — don't create multiple Settings()
settings = Settings()
