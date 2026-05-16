"""
AI-enhanced data processing layer.

Modules:
    llm_client: Multi-provider LLM API wrapper (DeepSeek / OpenAI / GLM / Ollama)
    schema_inferrer: Auto field descriptions from CSV samples via LLM
    text_to_sql: Natural language → SQL via LangChain RAG
"""

from .llm_client import LLMClient, load_llm_config
from .schema_inferrer import SchemaInferrer
from .text_to_sql import TextToSQLEngine

__all__ = ["LLMClient", "load_llm_config", "SchemaInferrer", "TextToSQLEngine"]
