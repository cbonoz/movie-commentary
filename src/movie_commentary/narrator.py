import os
import re

from openai import OpenAI

XAI_BASE_URL = "https://api.x.ai/v1"
MODEL = "grok-4.4"
DEFAULT_LINES = 5


def _api_key() -> str | None:
    return os.environ.get("XAI_API_KEY") or None


def _build_prompt(
    movie_label: str,
    scene_label: str,
    key_line: str,
    themes: str,
    raw_items: list[str],
    n: int = DEFAULT_LINES,
) -> str:
    items_text = "\n".join(f"- {t}" for t in raw_items if t) if raw_items else "(none)"
    return (
        f"You are writing TikTok video narration for the scene \"{scene_label}\" "
        f"from the film {movie_label}.\n\n"
        f"## Context\n"
        f"- Film: {movie_label}\n"
        f"- Scene: {scene_label}\n"
        f"- Key dialogue: \"{key_line}\"\n"
        f"- Themes: {themes}\n\n"
        f"## Raw web search results (may contain poor data)\n{items_text}\n\n"
        f"## Instructions\n"
        f"1. IGNORE low-quality or irrelevant search results entirely\n"
        f"2. Write {n} original, engaging narration lines based on YOUR own knowledge "
        f"of this film and scene\n"
        f"3. Each line: complete sentence, under 20 words, natural and conversational\n"
        f"4. The narration should sound like an insightful film fan commenting on the scene\n"
        f"5. Cover: acting, directing, behind-the-scenes trivia, themes, or cultural impact\n"
        f"6. Vary the sentence structure — don't start every line the same way\n"
        f"7. No introductory phrases like 'Here are...', no quotes, no hashtags, no markdown\n\n"
        f"Return exactly {n} lines, one per line, nothing else."
    )


def narrate(
    movie_label: str,
    scene_label: str,
    key_line: str = "",
    themes: str = "",
    raw_items: list[str] | None = None,
) -> list[str]:
    if raw_items is None:
        raw_items = []

    key = _api_key()
    if not key:
        # No API — return cleaned raw items as fallback
        cleaned = []
        for t in raw_items:
            t = re.sub(r"^[A-Z][a-z]+ \d{1,2}, \d{4}\s*[·•]?\s*", "", t).strip()
            if len(t) > 25:
                cleaned.append(t)
            if len(cleaned) >= DEFAULT_LINES:
                break
        return cleaned[:DEFAULT_LINES]

    client = OpenAI(api_key=key, base_url=XAI_BASE_URL)
    prompt = _build_prompt(movie_label, scene_label, key_line, themes, raw_items)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You write tight, insightful TikTok narration. Return only the requested lines."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        text = resp.choices[0].message.content.strip()
        lines = [l.strip().strip('"').strip("'") for l in text.split("\n") if l.strip()]
        return lines[:DEFAULT_LINES]
    except Exception:
        return narrate(movie_label, scene_label, key_line, themes, raw_items)
