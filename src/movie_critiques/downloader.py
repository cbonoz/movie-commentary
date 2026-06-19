import json
import subprocess
import re
from pathlib import Path


def search_youtube(query: str, max_results: int = 10) -> list[dict]:
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--dump-json", f"ytsearch{max_results}:{query}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {result.stderr.strip()}")
    entries = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def score_result(entry: dict, min_duration: float = 30, max_duration: float = 300) -> float:
    dur = entry.get("duration") or 0
    views = entry.get("view_count") or 0
    title = entry.get("title") or ""

    if dur < min_duration or dur > max_duration:
        return -1

    dur_score = 1.0 if 60 <= dur <= 180 else 0.3
    view_score = min(views / 500_000, 1.0)
    scene_bonus = 0.2 if re.search(r"\bscene\b", title, re.I) else 0.0
    hd_bonus = 0.1 if re.search(r"\b(1080|720|HD)\b", title, re.I) else 0.0

    return dur_score * 0.4 + view_score * 0.3 + scene_bonus + hd_bonus


def pick_best(entries: list[dict]) -> dict | None:
    scored = [(score_result(e), e) for e in entries]
    valid = [(s, e) for s, e in scored if s > 0]
    if not valid:
        return None
    valid.sort(key=lambda x: x[0], reverse=True)
    return valid[0][1]


def download(url_or_id: str, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(title)s.%(ext)s")

    result = subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
            "--merge-output-format", "mp4",
            "--max-filesize", "500M",
            "--extractor-args", "youtube:player_client=android",
            "-o", template,
            "--print", "after_move:filepath",
            url_or_id,
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {result.stderr.strip()}")
    out = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else None
    if not out or not Path(out).exists():
        raise RuntimeError("yt-dlp did not produce an output file")
    return Path(out)
