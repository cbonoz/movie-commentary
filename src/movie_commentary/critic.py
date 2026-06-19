import re
import time
import json
import urllib.request
from typing import Any

from ddgs import DDGS


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lstrip("'\"„,;:-–—").rstrip("'\"„,;:-–—")
    return text


def _condense(text: str, max_chars: int = 140) -> str | None:
    text = _clean(text)
    if not text or len(text) < 30:
        return None
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    for delimiter in (".", "!", "?"):
        pos = truncated.rfind(delimiter)
        if pos > max_chars // 2:
            return truncated[: pos + 1]
    last_space = truncated.rfind(" ")
    return (truncated[:last_space] + ".") if last_space > 0 else truncated + "..."


def _is_poor(text: str | None) -> bool:
    if not text or len(text) < 30:
        return True
    lower = text.lower()
    poor_keywords = ["subscribe", "smoothie", "follow @", "click here", "shop now",
                     "buy now", "sign up", "newsletter", "promotion", "yarn is the best"]
    if any(kw in lower for kw in poor_keywords):
        return True
    if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}", text):
        return False
    if text.count("...") > 2:
        return True
    if text.startswith(",") or text.startswith(".") or text.startswith("'"):
        return True
    return False


def _is_dialogue(text: str) -> bool:
    lower = text.lower()
    if ":" in text[:30] and not re.search(r"\b(film|movie|scene|director|analysis)\b", lower):
        return True
    if re.match(r'^["\']', text):
        return True
    return False


def _score(text: str) -> int:
    if _is_dialogue(text):
        return -10
    score = 0
    if re.search(r"[A-Z][a-z]+", text):
        score += 2
    if len(text) > 80:
        score += 2
    if not re.match(r"^\d{4}", text[:6]):
        score += 1
    if "film" in text.lower() or "movie" in text.lower():
        score += 1
    if "tarantino" in text.lower() or "nolan" in text.lower() or "scorsese" in text.lower():
        score += 2
    if text.count("...") == 0:
        score += 1
    return score


def _fetch_wikipedia(movie: str) -> list[str]:
    try:
        encoded = urllib.request.quote(movie.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "movie-critiques/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError:
            url2 = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}_%28film%29"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "movie-critiques/0.1"})
            with urllib.request.urlopen(req2, timeout=5) as resp2:
                data = json.loads(resp2.read())
        extract = data.get("extract", "")
        if not extract:
            return []
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", extract) if len(s.strip()) > 50]
        return sentences[:6]
    except Exception:
        return []


_wiki_cache: dict[str, list[str]] = {}


def _get_wiki_snippets(movie: str) -> list[str]:
    if movie not in _wiki_cache:
        _wiki_cache[movie] = _fetch_wikipedia(movie)
        time.sleep(0.3)
    return _wiki_cache[movie]


def commentary_on_line(movie: str, line: str) -> str | None:
    if len(line) < 10:
        return None

    queries = [
        f'"{movie}" "{line}" scene analysis',
        f'"{movie}" "{line}" behind the scenes',
        f'"{movie}" "{line}" film critique',
    ]

    for query in queries:
        try:
            time.sleep(0.5)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
        except Exception:
            continue
        for r in results:
            body = r.get("body", "") or r.get("snippet", "")
            condensed = _condense(body)
            if not _is_poor(condensed):
                return condensed

    wiki = _get_wiki_snippets(movie)
    if wiki:
        return wiki[0]
    return None


def batch_commentary(movie: str, segments: list[dict]) -> list[dict]:
    enriched: list[dict[str, Any]] = []
    for seg in segments:
        text = seg["text"].strip()
        seg["commentary"] = commentary_on_line(movie, text) if text else None
        enriched.append(seg)
    return enriched


def pick_best(commentaries: list[str], n: int = 5) -> list[str]:
    scored = sorted(commentaries, key=_score, reverse=True)
    return scored[:n]


def pick_best_segments(segments: list[dict], n: int = 5) -> list[dict]:
    with_comm = [s for s in segments if s.get("commentary")]
    scored = sorted(with_comm, key=lambda s: _score(s["commentary"]), reverse=True)
    return scored[:n]
