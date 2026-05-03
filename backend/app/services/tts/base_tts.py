# =============================================================================
# backend/app/services/tts/base_tts.py
# Abstract interface for Text-to-Speech providers.
# Week 1: Stub. Week 3: Implemented with Web Speech API signals.
# =============================================================================
from abc import ABC, abstractmethod


class BaseTTS(ABC):
    @abstractmethod
    def get_speak_signal(self, text: str, speaker: str) -> dict:
        """
        Return the WS message to send to frontend to trigger TTS.
        Frontend useSTT.ts listens for this and calls speechSynthesis.speak().
        """
        ...
