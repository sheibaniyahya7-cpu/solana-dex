"""
Base AI agent class.
All agents inherit from this, getting a shared OpenAI client,
structured output parsing, token tracking, and error handling.
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import settings
from app.core.logging import get_logger


class BaseAgent(ABC):
    """
    Abstract base for all AI analysis agents.
    Each agent receives structured data, calls the LLM, and returns
    a typed analysis dict.
    """

    name: str = "base_agent"
    system_prompt: str = "You are a professional crypto trading analyst."
    model: str = ""  # Set per-agent; defaults to settings.OPENAI_MODEL

    def __init__(self) -> None:
        self.logger = get_logger(f"agent.{self.name}")
        self._client: Optional[AsyncOpenAI] = None
        self.model = self.model or settings.OPENAI_MODEL

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_REQUEST_TIMEOUT,
            )
        return self._client

    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main analysis method.
        Receives a context dict with all relevant data for this agent.
        Returns a structured analysis dict.
        """
        ...

    async def _call_llm(
        self,
        user_message: str,
        system_override: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> tuple[Optional[str], int]:
        """
        Call the OpenAI API.
        Returns (response_text, tokens_used).
        """
        if not settings.OPENAI_API_KEY:
            self.logger.warning("OpenAI API key not configured — returning stub response")
            return self._stub_response(), 0

        messages = [
            {
                "role": "system",
                "content": system_override or self.system_prompt,
            },
            {"role": "user", "content": user_message},
        ]

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.OPENAI_TEMPERATURE,
            "max_tokens": max_tokens or settings.OPENAI_MAX_TOKENS,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            start = time.perf_counter()
            response: ChatCompletion = await self.client.chat.completions.create(**kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0

            self.logger.debug(
                "LLM call complete",
                agent=self.name,
                tokens=tokens,
                duration_ms=round(elapsed_ms),
            )
            return content, tokens

        except Exception as e:
            self.logger.error("LLM call failed", agent=self.name, error=str(e))
            return None, 0

    def _parse_json_response(self, text: Optional[str]) -> Optional[Dict]:
        """Extract and parse JSON from LLM response."""
        if not text:
            return None
        # Strip markdown code blocks if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from mixed text
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            self.logger.warning("JSON parse failed", agent=self.name, text=text[:100])
            return None

    def _stub_response(self) -> str:
        """Return a minimal stub when no API key is configured."""
        return json.dumps({
            "score": 50,
            "summary": "Analysis unavailable — OpenAI API key not configured.",
            "signals": [],
            "risks": [],
            "decision": "WATCH",
            "confidence": 0.5,
        })
