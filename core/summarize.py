# core/summarize.py
from __future__ import annotations
import os
import re
import requests
from pathlib import Path
from typing import Callable, Optional, Dict, List

from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM

# Import configuration from the centralized config module
try:
    from config import (
        MODEL_NAME, ONLINE_MODE_MAX_CHARS, ONLINE_MODE_MAX_WORDS,
        OFFLINE_MODE_MAX_CHARS, OFFLINE_MODE_MAX_WORDS
    )
except ImportError:
    # Fallback configuration if config.py doesn't exist
    MODEL_NAME = "sshleifer/distilbart-cnn-12-6"
    ONLINE_MODE_MAX_CHARS = 4000
    ONLINE_MODE_MAX_WORDS = 800
    OFFLINE_MODE_MAX_CHARS = 100000
    OFFLINE_MODE_MAX_WORDS = 20000

# ---------- constants & dirs ----------
MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)

LOCAL_MODEL_DIR = MODELS_DIR / "distilbart-cnn-12-6"

Progress = Optional[Callable[[str, int, int], None]]


# ---------- utilities ----------
def _chunk_text(text: str, max_words: int = 600) -> List[str]:
    """
    Split text into chunks ~max_words using sentence boundaries when possible.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: List[str] = []
    cur: List[str] = []
    cur_words = 0

    for s in sentences:
        w = len(s.split())
        if cur and cur_words + w > max_words:
            chunks.append(" ".join(cur))
            cur, cur_words = [s], w
        else:
            cur.append(s)
            cur_words += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks if chunks else [text.strip()]


def _count_words(text: str) -> int:
    return len(text.split())


def _count_chars(text: str) -> int:
    return len(text)


def _within_limits(text: str, mode: str) -> (bool, str):
    words, chars = _count_words(text), _count_chars(text)
    if mode == "online":
        if words > ONLINE_MODE_MAX_WORDS or chars > ONLINE_MODE_MAX_CHARS:
            return False, f"Text exceeds online mode limits (max {ONLINE_MODE_MAX_WORDS} words or {ONLINE_MODE_MAX_CHARS} chars)."
    else:
        if words > OFFLINE_MODE_MAX_WORDS or chars > OFFLINE_MODE_MAX_CHARS:
            return False, f"Text exceeds offline mode limits (max {OFFLINE_MODE_MAX_WORDS} words or {OFFLINE_MODE_MAX_CHARS} chars)."
    return True, ""


# ---------- model management ----------
def download_model() -> Path:
    """
    Download the offline model locally so the pipeline can run without internet.
    """
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(LOCAL_MODEL_DIR)
    model.save_pretrained(LOCAL_MODEL_DIR)
    return LOCAL_MODEL_DIR


def get_model_path() -> Path:
    """
    Return local model path, downloading if missing.
    """
    if not LOCAL_MODEL_DIR.exists():
        return download_model()
    return LOCAL_MODEL_DIR


# ---------- main API ----------
def summarize_text(
    text: str,
    min_length: int,
    max_length: int,
    config: Dict[str, str],
    progress_callback: Progress = None,
) -> str:
    """
    Summarize given text according to mode:
      - offline: uses local Transformers pipeline, downloads model if missing
      - online: uses Hugging Face Inference API (requires config['api_key'])

    Arguments:
      text: input text
      min_length, max_length: summary token lengths (roughly)
      config: {'mode': 'offline'|'online', 'api_key': optional}
      progress_callback(stage: str, step: int, total: int): optional progress hook
    """
    mode = (config.get("mode") or "offline").lower()

    ok, msg = _within_limits(text, mode)
    if not ok:
        # If online is too small, auto-fallback to offline (more permissive)
        if mode == "online":
            mode = "offline"
            if progress_callback:
                progress_callback("Switching to offline mode due to size limits", 0, 0)
        else:
            # Too large even for offline; caller should trim or chunk more aggressively
            raise ValueError(msg)

    # Chunk the text to keep each call within bounds and merge summaries
    # Use smaller chunks online to respect tighter limits
    chunk_words = 350 if mode == "online" else 800
    chunks = _chunk_text(text, max_words=chunk_words)
    summaries: List[str] = []
    total = len(chunks)

    if mode == "offline":
        if progress_callback:
            progress_callback("Preparing offline model", 0, total)
        model_dir = get_model_path()
        
        # Load tokenizer and model manually for cross-version compatibility
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        model = AutoModelForSeq2SeqLM.from_pretrained(model_dir)
        
        # Force CPU device
        device = "cpu"
        model = model.to(device)
        
        import torch
        
        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback("Summarizing chunks (offline)", i, total)
            
            inputs = tokenizer(
                chunk,
                max_length=1024,
                truncation=True,
                return_tensors="pt"
            ).to(device)
            
            with torch.no_grad():
                summary_ids = model.generate(
                    inputs["input_ids"],
                    max_length=max_length,
                    min_length=min_length,
                    num_beams=4,
                    early_stopping=True
                )
            
            out = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            summaries.append(out.strip())
    else:
        # online via HF Inference API
        api_key = (config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key not set for online mode.")
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = f"https://api-inference.huggingface.co/models/{MODEL_NAME}"

        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback("Contacting HF API (online)", i, total)
            r = requests.post(
                api_url,
                headers=headers,
                json={"inputs": chunk, "parameters": {"max_length": max_length, "min_length": min_length, "do_sample": False}},
                timeout=60,
            )
            if r.status_code != 200:
                raise RuntimeError(f"HF API error: {r.status_code} {r.text[:200]}")
            data = r.json()
            # Some HF hosts return a list of dicts [{'summary_text': ...}]
            if isinstance(data, list) and data and "summary_text" in data[0]:
                summaries.append(data[0]["summary_text"])
            else:
                # Fallback: try to parse other shapes or raise
                raise RuntimeError(f"Unexpected HF response: {str(data)[:200]}")

    final = " ".join(summaries).strip()
    if progress_callback:
        progress_callback("Summarization done", total, total)
    return final