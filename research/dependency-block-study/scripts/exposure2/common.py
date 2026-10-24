"""Shared definitions for exposure study 2 (expansion/EXPOSURE2_PROTOCOL.md)."""
import os
import re
from pathlib import Path

RW2 = Path(os.environ.get("REALWORLD2_DIR", "since_cutoff_runs/realworld2"))
RW1 = Path(os.environ.get("REALWORLD_DIR", "since_cutoff_runs/realworld"))
SC = Path(os.environ.get("CUTOFFNOTES_EXE", "since_cutoff_runs/scan-venv/Scripts/since-cutoff.exe"))
CUTOFF = "2026-06-30"
MODEL = "anthropic:claude-opus-5-5"
SEED_ORDER = 20261023
SEED_AUDIT = 20261024
SEED_BOOT = 20261023
N_PER_STRATUM = 100
SCAN_TIMEOUT = 1200
CLONE_TIMEOUT = 600
MAX_SIZE_KB = 2_000_000
AUTHOR_OWNER = "MohammadHijjawi97"

AI_EXACT = {
    "openai", "anthropic", "google-genai", "google-generativeai", "google-cloud-aiplatform", "google-adk",
    "mistralai", "cohere", "groq", "together", "fireworks-ai", "litellm", "ollama", "vllm", "llama-cpp-python",
    "langchain", "langgraph", "langsmith", "llama-index", "transformers", "sentence-transformers", "huggingface-hub",
    "datasets", "tokenizers", "tiktoken", "peft", "trl", "accelerate", "diffusers", "mcp", "fastmcp", "pydantic-ai",
    "pydantic-ai-slim", "instructor", "dspy", "dspy-ai", "crewai", "smolagents", "autogen-agentchat", "autogen-core",
    "pyautogen", "ag2", "openai-agents", "claude-agent-sdk", "agno", "haystack-ai", "semantic-kernel", "guidance",
    "outlines", "chromadb", "qdrant-client", "pinecone", "pinecone-client", "weaviate-client", "pymilvus", "lancedb",
    "mem0ai", "letta", "browser-use",
}
AI_PREFIX = ("langchain-", "langgraph-", "llama-index-")

LOCKFILES = ("uv.lock", "poetry.lock", "pdm.lock", "pylock.toml", "Pipfile.lock")
SPARSE = ["*.py*", "*.toml", "*.lock", "requirements*.txt", "requirements/*.txt", "Pipfile", "Pipfile.lock",
          ".python-version", "/*.md"]

SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL")


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def is_ai(name: str) -> bool:
    c = canon(name)
    return c in AI_EXACT or c.startswith(AI_PREFIX)


def is_pinned(entry: dict) -> bool:
    vs = (entry.get("version_source") or "")
    return bool(vs) and not vs.startswith("latest on PyPI") and vs != "unpinned"


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in SECRET_MARKERS)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def slug(full_name: str) -> str:
    return full_name.replace("/", "__")
