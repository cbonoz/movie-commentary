import subprocess
import os
import re
from pathlib import Path


def find_best_segment(segments: list[dict], phrase: str) -> tuple[float, float] | None:
    phrase_lower = phrase.lower().strip()
    best = None
    for seg in segments:
        text = seg["text"].strip()
        if phrase_lower in text.lower():
            score = len(text)
            if best is None or score < best[0]:
                best = (score, seg["start"], seg["end"])
    if best:
        return (best[1], best[2])
    return None


def find_richest_segment(segments: list[dict], min_words: int = 5) -> tuple[float, float] | None:
    valid = [(s["start"], s["end"], len(s["text"].split()))
             for s in segments if len(s["text"].split()) >= min_words]
    if not valid:
        return None
    valid.sort(key=lambda x: x[2], reverse=True)
    return (valid[0][0], valid[0][1])


def merge_segments(segments: list[dict], min_gap: float = 0.5, max_block: float = 8.0) -> list[dict]:
    if not segments:
        return []
    merged = [dict(segments[0])]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg["start"] - prev["end"]
        new_dur = seg["end"] - prev["start"]
        if gap < min_gap and new_dur <= max_block:
            prev["end"] = seg["end"]
            prev["text"] = prev["text"] + " " + seg["text"]
        else:
            merged.append(dict(seg))
    return merged


def cut_segment(
    video_path: str | Path,
    start: float,
    end: float,
    output_path: str | Path,
):
    dur = end - start
    subprocess.run(
        ["ffmpeg", "-ss", str(start), "-i", str(video_path),
         "-t", str(dur),
         "-c:v", "libx264", "-preset", "fast", "-crf", "22",
         "-c:a", "aac",
         "-y", str(output_path)],
        capture_output=True, text=True, check=True,
    )


def get_audio(video_path: str | Path, output_path: str | Path):
    subprocess.run(
        ["ffmpeg", "-i", str(video_path),
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
         "-y", str(output_path)],
        capture_output=True, text=True, check=True,
    )
