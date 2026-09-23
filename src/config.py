"""
config.py — Load and validate all environment variables from .env

Every module imports `cfg` from here — never calls os.getenv directly.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (parent of this src/ directory)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path, override=True)


class Config:
    # ── LLM providers
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "").strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    GEMINI_REASONING_EFFORT: str = os.getenv("GEMINI_REASONING_EFFORT", "medium").strip()
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "").strip()

    # ── Agent identity
    AGENT_NAME: str = os.getenv("AGENT_NAME", "my-earn-agent").strip()
    AGENT_USERNAME: str = os.getenv("AGENT_USERNAME", "").strip()

    # ── Superteam
    SUPERTEAM_API_KEY: str = os.getenv("SUPERTEAM_API_KEY", "").strip()
    SUPERTEAM_CLAIM_CODE: str = os.getenv("SUPERTEAM_CLAIM_CODE", "").strip()
    SUPERTEAM_CLAIM_URL: str = os.getenv("SUPERTEAM_CLAIM_URL", "").strip()

    # ── Wallets (public addresses only — never private keys)
    EVM_WALLET: str = os.getenv("EVM_WALLET", "").strip()
    SOL_WALLET: str = os.getenv("SOL_WALLET", "").strip()

    # ── GitHub (optional, for automatic PR creation)
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "").strip()
    GITHUB_USERNAME: str = os.getenv("GITHUB_USERNAME", "").strip()

    @classmethod
    def reload(cls) -> None:
        """Re-read .env (call after installer writes a new .env)."""
        load_dotenv(_env_path, override=True)
        for attr in [
            "NVIDIA_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_REASONING_EFFORT",
            "GROQ_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY", "AGENT_NAME",
            "AGENT_USERNAME", "SUPERTEAM_API_KEY", "SUPERTEAM_CLAIM_CODE",
            "SUPERTEAM_CLAIM_URL", "EVM_WALLET", "SOL_WALLET",
            "GITHUB_TOKEN", "GITHUB_USERNAME",
        ]:
            setattr(cls, attr, os.getenv(attr, "").strip())

    @classmethod
    def available_providers(cls) -> list[str]:
        """Return list of provider names that have a key configured."""
        providers = []
        if cls.NVIDIA_API_KEY:
            providers.append("NVIDIA")
        if cls.GEMINI_API_KEY:
            providers.append("Gemini")
        if cls.GROQ_API_KEY:
            providers.append("Groq")
        if cls.OPENAI_API_KEY:
            providers.append("OpenAI")
        if cls.PERPLEXITY_API_KEY:
            providers.append("Perplexity")
        return providers

    @classmethod
    def has_llm(cls) -> bool:
        return bool(cls.available_providers())

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of validation error strings (empty = all OK)."""
        issues: list[str] = []
        if not cls.has_llm():
            issues.append(
                "No LLM API key found. Add at least one of: "
                "NVIDIA_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY"
            )
        if not cls.EVM_WALLET and not cls.SOL_WALLET:
            issues.append("No wallet address configured (EVM_WALLET or SOL_WALLET required)")
        return issues


cfg = Config()
