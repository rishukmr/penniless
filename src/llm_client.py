"""
llm_client.py — Multi-provider LLM client with automatic fallback

Fallback order (configurable via .env):
  1. NVIDIA   — deepseek-ai/deepseek-v4.1-flash (nvapi key)
  2. Gemini   — gemini-3.8-flash / gemini-2.5-flash (Google AI key, auto-fallback)
  3. Groq     — qwen/qwen3.8-27b                    (groq key)
  4. OpenAI   — gpt-4o-mini                          (openai key)
  5. Perplexity — llama-3.1-sonar-large              (pplx key)

All five providers expose an OpenAI-compatible /v1/chat/completions endpoint,
so we use a single `openai.OpenAI` client configured with the right base_url
and api_key per provider — no extra SDKs needed.
"""
from __future__ import annotations

import sys
# Force UTF-8 output on Windows (prevents cp1252 emoji encoding errors)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dataclasses import dataclass, field
from typing import Optional
import openai
from rich.console import Console

from src.config import cfg

console = Console()


# ─── Provider registry ────────────────────────────────────────────────────────

@dataclass
class Provider:
    name: str
    api_key: str
    base_url: str
    model: str
    extra_params: dict = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# Ordered list — first enabled provider is tried first.
# To change priority, reorder this list.
# Models verified working as of 2026-09-24.
_ALL_PROVIDERS: list[Provider] = [
    Provider(
        name="NVIDIA",
        api_key=cfg.NVIDIA_API_KEY,
        base_url="https://integrate.api.nvidia.com/v1",
        # deepseek-ai/deepseek-v4.1-flash — verified working with new NVIDIA key (~13s non-streaming)
        model="deepseek-ai/deepseek-v4.1-flash",
    ),
    Provider(
        name="Gemini",
        api_key=cfg.GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        # Gemini 3.8 Flash with medium reasoning effort (with auto-fallback to 2.5-flash on quota)
        model=cfg.GEMINI_MODEL,
        extra_params={"reasoning_effort": cfg.GEMINI_REASONING_EFFORT},
    ),
    Provider(
        name="Groq",
        api_key=cfg.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        # qwen/qwen3.8-27b — top coding & reasoning model on Groq
        model="qwen/qwen3.8-27b",
    ),
    Provider(
        name="OpenAI",
        api_key=cfg.OPENAI_API_KEY,
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    ),
    Provider(
        name="Perplexity",
        api_key=cfg.PERPLEXITY_API_KEY,
        base_url="https://api.perplexity.ai",
        model="llama-3.1-sonar-large-128k-online",
    ),
]


# ─── Client ───────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Sends chat messages to the first available LLM provider.
    On any error, automatically falls back to the next provider in the list.

    Usage:
        from src.llm_client import llm
        reply = llm.chat([{"role": "user", "content": "Hello"}])
    """

    def __init__(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        """Re-evaluate which providers are enabled (call after config reload)."""
        # Sync provider keys with current config values
        _ALL_PROVIDERS[0].api_key = cfg.NVIDIA_API_KEY
        _ALL_PROVIDERS[1].api_key = cfg.GEMINI_API_KEY
        _ALL_PROVIDERS[1].model = cfg.GEMINI_MODEL
        _ALL_PROVIDERS[1].extra_params = {"reasoning_effort": cfg.GEMINI_REASONING_EFFORT}
        _ALL_PROVIDERS[2].api_key = cfg.GROQ_API_KEY
        _ALL_PROVIDERS[3].api_key = cfg.OPENAI_API_KEY
        _ALL_PROVIDERS[4].api_key = cfg.PERPLEXITY_API_KEY
        self.providers = [p for p in _ALL_PROVIDERS if p.enabled]

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        silent: bool = False,
    ) -> str:
        """
        Send a chat request and return the assistant reply as a string.

        Args:
            messages:    List of {"role": "user"|"assistant", "content": "..."} dicts.
            system:      Optional system prompt prepended automatically.
            max_tokens:  Maximum tokens in the reply.
            temperature: Sampling temperature (lower = more deterministic).
            silent:      If True, suppress provider-selection output.

        Returns:
            The assistant's reply as a plain string.

        Raises:
            RuntimeError: if every configured provider fails.
        """
        if not self.providers:
            raise RuntimeError(
                "No LLM provider configured. "
                "Add at least one API key to .env (NVIDIA_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, …)"
            )

        full_messages: list[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        last_error: Exception | None = None

        for provider in self.providers:
            try:
                if not silent:
                    effort_tag = f" (effort: {provider.extra_params.get('reasoning_effort')})" if provider.extra_params.get('reasoning_effort') else ""
                    console.print(
                        f"  [dim]-> [{provider.name}] {provider.model}{effort_tag}[/dim]"
                    )
                client = openai.OpenAI(
                    api_key=provider.api_key,
                    base_url=provider.base_url,
                    timeout=120,
                )
                create_kwargs = {
                    "model": provider.model,
                    "messages": full_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if provider.extra_params:
                    create_kwargs.update(provider.extra_params)

                try:
                    response = client.chat.completions.create(**create_kwargs)
                except openai.RateLimitError as rle:
                    # If Gemini 3.8 hits quota/rate limit, auto-fallback to gemini-2.5-flash
                    if provider.name == "Gemini" and provider.model != "gemini-2.5-flash":
                        console.print(f"  [yellow]⚠ Gemini: {provider.model} quota limit hit, auto-falling back to gemini-2.5-flash[/yellow]")
                        fallback_kwargs = dict(create_kwargs)
                        fallback_kwargs["model"] = "gemini-2.5-flash"
                        fallback_kwargs.pop("reasoning_effort", None)
                        response = client.chat.completions.create(**fallback_kwargs)
                    else:
                        raise rle
                except openai.BadRequestError as bre:
                    if provider.extra_params and "reasoning_effort" in create_kwargs:
                        create_kwargs.pop("reasoning_effort", None)
                        response = client.chat.completions.create(**create_kwargs)
                    else:
                        raise bre

                content = response.choices[0].message.content or ""
                if not content.strip():
                    raise ValueError(f"{provider.name} ({provider.model}) returned empty output")
                return content

            except openai.AuthenticationError as e:
                console.print(
                    f"  [red]✗ {provider.name}: authentication failed — check your API key[/red]"
                )
                last_error = e
            except openai.RateLimitError as e:
                console.print(f"  [yellow]⚠ {provider.name}: rate limit hit, trying next[/yellow]")
                last_error = e
            except openai.APIConnectionError as e:
                console.print(f"  [yellow]⚠ {provider.name}: connection error, trying next[/yellow]")
                last_error = e
            except Exception as e:
                console.print(f"  [yellow]⚠ {provider.name}: {type(e).__name__}: {e}[/yellow]")
                last_error = e

        raise RuntimeError(
            f"All LLM providers exhausted. Last error: {last_error}\n"
            "Check your API keys in .env"
        )

    def active_provider_names(self) -> list[str]:
        """Return names of all enabled providers in fallback order."""
        return [p.name for p in self.providers]

    def active_summary(self) -> str:
        """Human-readable summary of active providers."""
        if not self.providers:
            return "none"
        parts = [f"{p.name}({p.model.split('/')[-1]})" for p in self.providers]
        return " → ".join(parts)

    def test_all(self) -> dict[str, bool]:
        """
        Quick smoke-test every configured provider.
        Returns dict of {provider_name: success}.
        """
        results: dict[str, bool] = {}
        test_msg = [{"role": "user", "content": 'Reply with exactly: "OK"'}]

        for provider in self.providers:
            try:
                client = openai.OpenAI(
                    api_key=provider.api_key,
                    base_url=provider.base_url,
                    timeout=120,
                )
                kwargs = {
                    "model": provider.model,
                    "messages": test_msg,
                    "max_tokens": 200,
                    "temperature": 0.3,
                }
                if provider.extra_params:
                    kwargs.update(provider.extra_params)
                try:
                    resp = client.chat.completions.create(**kwargs)
                except openai.RateLimitError:
                    if provider.name == "Gemini":
                        kwargs["model"] = "gemini-2.5-flash"
                        kwargs.pop("reasoning_effort", None)
                        resp = client.chat.completions.create(**kwargs)
                    else:
                        raise
                except openai.BadRequestError:
                    kwargs.pop("reasoning_effort", None)
                    resp = client.chat.completions.create(**kwargs)

                results[provider.name] = bool((resp.choices[0].message.content or "").strip())
            except Exception:
                results[provider.name] = False
        return results


# ─── Singleton ────────────────────────────────────────────────────────────────
llm = LLMClient()
