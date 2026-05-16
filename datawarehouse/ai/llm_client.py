"""
Multi-provider LLM API client.

Supports: DeepSeek, OpenAI, GLM (ZhipuAI), Ollama (local).
Configuration is read from ``config/llm_config.yaml`` — API keys are NEVER
hardcoded and the config file is gitignored.

Usage::

    from datawarehouse.ai import LLMClient, load_llm_config

    config = load_llm_config()
    client = LLMClient(config)
    result = client.chat("Explain this CSV schema: ...")
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # type: ignore  # installed on first use

# Auto-install requests if missing
import sys
import subprocess

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "pyyaml", "--quiet"])
    import requests  # type: ignore
    import yaml  # type: ignore

logger = logging.getLogger("DataWarehouse.AI")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "llm_config.yaml"


def load_llm_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load LLM configuration from YAML file.

    Args:
        path: Path to ``llm_config.yaml``. Defaults to ``config/llm_config.yaml``
              relative to project root.

    Returns:
        Parsed configuration dict.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"LLM config not found at {config_path}. "
            f"Copy config/llm_config.yaml and fill in your API key."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class LLMClient:
    """Multi-provider LLM API client with rate limiting and retry logic.

    Providers are configured via ``llm_config.yaml``. API keys are read from
    the config file — never embed keys in code or commit them to git.

    Args:
        config: Parsed YAML config dict from :func:`load_llm_config`.
        provider_override: Optional provider name to use instead of the config's
                           ``active_provider``.
    """

    def __init__(self, config: Dict[str, Any], provider_override: Optional[str] = None) -> None:
        provider_name = provider_override or config.get("active_provider", "deepseek")
        providers = config.get("providers", {})
        if provider_name not in providers:
            raise ValueError(
                f"Unknown provider '{provider_name}'. "
                f"Available: {list(providers.keys())}"
            )
        self._provider = providers[provider_name]
        self._provider_name = provider_name
        self._base_url = self._provider["base_url"].rstrip("/")
        self._api_key = self._provider.get("api_key", "")
        self._model = self._provider.get("model", "deepseek-chat")
        self._max_tokens = self._provider.get("max_tokens", 4096)
        self._temperature = self._provider.get("temperature", 0.1)

        rate_cfg = config.get("rate_limit", {})
        self._rpm = rate_cfg.get("requests_per_minute", 30)
        self._max_retries = rate_cfg.get("max_retries", 3)
        self._retry_delay = rate_cfg.get("retry_delay_seconds", 5)

        # For Ollama, no API key needed
        if provider_name == "ollama":
            self._api_key = "ollama"  # placeholder

        logger.info("LLM client initialized: provider=%s model=%s", provider_name, self._model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, prompt: str, system_prompt: str = "",
             temperature: Optional[float] = None) -> str:
        """Send a chat completion request and return the response text.

        Args:
            prompt: User message content.
            system_prompt: Optional system-level instruction.
            temperature: Override the default temperature.

        Returns:
            The model's text response.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self._request_with_retry(messages, temperature)

    def chat_json(self, prompt: str, system_prompt: str = "",
                  temperature: Optional[float] = None) -> Dict[str, Any]:
        """Send a chat request and parse the response as JSON.

        The prompt should instruct the model to return valid JSON.
        """
        for _ in range(self._max_retries):
            raw = self.chat(prompt, system_prompt, temperature)
            # Try to extract JSON from the response
            try:
                # Handle markdown code blocks
                if "```json" in raw:
                    start = raw.index("```json") + 7
                    end = raw.index("```", start)
                    raw = raw[start:end].strip()
                elif "```" in raw:
                    start = raw.index("```") + 3
                    end = raw.index("```", start)
                    raw = raw[start:end].strip()
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse JSON from response, retrying...")
                continue
        raise RuntimeError("Failed to get valid JSON from LLM after all retries")

    def infer_schema(self, headers: List[str], sample_rows: List[List[str]]) -> Dict[str, Any]:
        """Infer field descriptions for CSV columns using LLM.

        Args:
            headers: Column header names.
            sample_rows: First 5-10 rows of data.

        Returns:
            Dict mapping column name → {{description, type_guess, nullable, ...}}.
        """
        prompt = _build_schema_prompt(headers, sample_rows)
        system = (
            "You are a data engineer. Analyze CSV columns and return a JSON object. "
            "For each column, provide: description (business meaning in Chinese), "
            "type_guess (string/int/float/date/boolean), nullable (true/false based on samples), "
            "category (dimension/measure/timestamp/id). "
            "Return ONLY valid JSON, no markdown, no explanation."
        )
        return self.chat_json(prompt, system, temperature=0.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request_with_retry(self, messages: List[Dict[str, str]],
                            temperature: Optional[float] = None) -> str:
        """Send request with rate limiting and exponential backoff."""
        endpoint = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        body = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": temperature if temperature is not None else self._temperature,
        }

        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    endpoint, headers=headers, json=body,
                    timeout=60,
                )
                if resp.status_code == 429:
                    # Rate limited — wait and retry
                    wait = self._retry_delay * (2 ** attempt)
                    logger.warning("Rate limited by %s, waiting %ds...",
                                   self._provider_name, wait)
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.error("LLM API error %d: %s", resp.status_code, resp.text[:200])
                    raise RuntimeError(f"LLM API returned {resp.status_code}: {resp.text[:200]}")

                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()

            except (requests.RequestException, KeyError, IndexError) as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    wait = self._retry_delay * (2 ** attempt)
                    logger.warning("LLM request failed (attempt %d/%d): %s",
                                   attempt + 1, self._max_retries, exc)
                    time.sleep(wait)
                continue

        raise RuntimeError(
            f"LLM request failed after {self._max_retries} attempts. "
            f"Last error: {last_error}"
        )

    @property
    def provider(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model


def _build_schema_prompt(headers: List[str], sample_rows: List[List[str]]) -> str:
    """Build a prompt for schema inference."""
    rows_str = "\n".join(
        "  " + " | ".join(str(c) for c in row)
        for row in sample_rows[:10]
    )
    return f"""Analyze these CSV columns and provide field descriptions.

Columns: {', '.join(headers)}

Sample data (first {len(sample_rows)} rows):
{rows_str}

Return a JSON object where each key is a column name, value is:
{{
    "description": "业务含义 (in Chinese)",
    "type_guess": "string|int|float|date|boolean",
    "nullable": true/false,
    "category": "dimension|measure|timestamp|id"
}}

Return ONLY valid JSON, no markdown wrapping."""
