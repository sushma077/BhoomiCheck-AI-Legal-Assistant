"""Replaceable model providers behind one interface, with honest reporting of what ran.

Order: Anthropic API key, local Ollama, local MLX model, then no model at all.
Keys are read from the environment and are never logged or stored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import requests

import config

NO_MODEL = "none (deterministic rules and retrieval)"


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str


class Provider:
    name = "none"
    model = NO_MODEL
    reliable_in_indian_languages = False  # small local models failed this in testing; see DEVELOPMENT_LOG.md

    @property
    def available(self) -> bool:
        return False

    def generate(self, system: str, prompt: str, max_tokens: int = 500) -> LLMResponse:
        raise RuntimeError("No language model is configured.")


class AnthropicProvider(Provider):
    name = "anthropic"
    reliable_in_indian_languages = True

    def __init__(self) -> None:
        self.model = config.ANTHROPIC_MODEL

    @property
    def available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    def generate(self, system: str, prompt: str, max_tokens: int = 500) -> LLMResponse:
        import anthropic

        message = anthropic.Anthropic().messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(text, self.model, self.name)


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self) -> None:
        self.model = config.OLLAMA_MODEL

    @property
    def available(self) -> bool:
        try:
            tags = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2).json().get("models", [])
        except (requests.RequestException, ValueError):
            return False
        if not tags:
            return False
        if not self.model:
            self.model = tags[0]["name"]
        return True

    def generate(self, system: str, prompt: str, max_tokens: int = 500) -> LLMResponse:
        resp = requests.post(f"{config.OLLAMA_HOST}/api/chat", timeout=300, json={
            "model": self.model, "stream": False, "options": {"num_predict": max_tokens, "temperature": 0.1},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        resp.raise_for_status()
        return LLMResponse(resp.json()["message"]["content"], self.model, self.name)


class MLXProvider(Provider):
    """Local model on Apple Silicon, used when BHOOMI_MLX_MODEL names a downloaded model."""
    name = "mlx"

    def __init__(self) -> None:
        self.model = config.MLX_MODEL
        self._loaded = None

    @property
    def available(self) -> bool:
        if not self.model:
            return False
        try:
            import mlx_lm  # noqa: F401
        except ImportError:
            return False
        return True

    def generate(self, system: str, prompt: str, max_tokens: int = 500) -> LLMResponse:
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler

        if self._loaded is None:
            self._loaded = load(self.model)
        model, tokenizer = self._loaded
        rendered = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            tokenize=False, add_generation_prompt=True)
        text = generate(model, tokenizer, prompt=rendered, max_tokens=max_tokens, sampler=make_sampler(temp=0.1))
        return LLMResponse(text.strip(), self.model, self.name)


@lru_cache(maxsize=1)
def get_provider() -> Provider:
    choices = {"anthropic": AnthropicProvider, "ollama": OllamaProvider, "mlx": MLXProvider}
    wanted = config.LLM_PROVIDER.lower()
    if wanted == "none":
        return Provider()
    if wanted in choices:
        provider = choices[wanted]()
        return provider if provider.available else Provider()
    for cls in (AnthropicProvider, OllamaProvider, MLXProvider):
        provider = cls()
        if provider.available:
            return provider
    return Provider()


def status() -> dict:
    provider = get_provider()
    return {"provider": provider.name, "model": provider.model if provider.available else NO_MODEL, "llm_available": provider.available}
