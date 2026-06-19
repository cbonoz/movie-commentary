import os
import re
from pathlib import Path

from openai import OpenAI

XAI_BASE_URL = "https://api.x.ai/v1"
N = 5
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def _load_key() -> str | None:
    return _env("XAI_API_KEY") or None


def _load_model() -> str:
    return _env("XAI_MODEL", "grok-4.3")


def _fallback_script(movie_label: str, scene_label: str, key_line: str, themes: str) -> list[str]:
    from . import critic
    base = f"The scene \"{scene_label}\" from {movie_label}"
    lines = [
        f"In this scene from {movie_label}, every moment is carefully crafted.",
        f"The dialogue — \"{key_line}\" — cuts to the heart of the film.",
    ]
    if themes:
        t = themes.split(",")[0].strip()
        lines.append(f"The theme of {t} runs through this entire sequence.")
    lines += [
        f"What makes this scene unforgettable is how it reveals character through action.",
        f"It's a masterclass in storytelling that rewards every rewatch.",
    ]
    return lines[:N]


def narrate(
    movie_label: str,
    scene_label: str,
    key_line: str = "",
    themes: str = "",
    raw_items: list[str] | None = None,
) -> list[str]:
    key = _load_key()

    if not key:
        return _fallback_script(movie_label, scene_label, key_line, themes)

    # Build prompt using ONLY scene context — no raw snippets to avoid copying garbage
    prompt = (
        f"Write {N} short lines of TikTok narration for a video about the scene "
        f"\"{scene_label}\" from {movie_label}.\n\n"
        f"Context: Film={movie_label}, Scene=\"{scene_label}\", "
        f"Key line=\"{key_line}\", Themes={themes}\n\n"
        f"Requirements:\n"
        f"- 5 lines total, each 8-18 words, complete sentences.\n"
        f"- Tell a mini-story: open with impact, give 2-3 sharp insights "
        f"(direction, performance, themes, behind-the-scenes), close with resonance.\n"
        f"- Do NOT describe what's visible on screen.\n"
        f"- Do NOT use quotes or dialogue from the film.\n"
        f"- No hashtags, no markdown, no numbering.\n"
        f"- Vary sentence openings — don't start every line the same way.\n"
        f"- The 5 lines together must feel like one continuous thought.\n\n"
        f"Return exactly 5 lines, one per line, nothing else."
    )

    client = OpenAI(api_key=key, base_url=XAI_BASE_URL)
    try:
        resp = client.chat.completions.create(
            model=_load_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.8,
        )
        text = resp.choices[0].message.content.strip()
        lines = [l.strip().strip('"').strip("'") for l in text.split("\n") if l.strip()]
        return lines[:N]
    except Exception:
        return _fallback_script(movie_label, scene_label, key_line, themes)
