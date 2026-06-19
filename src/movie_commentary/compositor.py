import subprocess
import textwrap
from pathlib import Path

from . import critic

PHASE_COUNT = 5
MIN_SECONDS = 4.0
FADE_CS = 25
WRAP_CHARS = 40
VIDEO_HEIGHT_RATIO = 0.50
PAD_TOP = 300
COMM_Y_OFFSET = 20


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    total_cs = int(seconds * 100)
    cs = total_cs % 100
    s = (total_cs // 100) % 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap(text: str) -> str:
    if not text:
        return ""
    wrapped = textwrap.wrap(text, width=WRAP_CHARS, break_long_words=False)
    return "\\N".join(wrapped) if wrapped else ""


def _esc(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}")


def _uniq(texts: list[str]) -> list[str]:
    seen = set()
    out = []
    for t in texts:
        sig = t.lower()[:40]
        if sig not in seen:
            seen.add(sig)
            out.append(t)
    return out


def generate_ass(
    segments: list[dict],
    output_path: str | Path,
    width: int = 1080,
    height: int = 1920,
    duration: float = 60.0,
    movie_label: str = "",
    scene_label: str = "",
):
    W, H = width, height
    safe_zone = int(H * VIDEO_HEIGHT_RATIO) + PAD_TOP  # bottom edge of video + pad
    cx = W // 2
    intro_end_t = min(5.0, duration)
    intro_end = _fmt_ts(intro_end_t)
    full_end = _fmt_ts(duration)

    lines = [
        "[Script Info]",
        "Title: Commentary Subtitles",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Alignment, MarginL, MarginR, MarginV",
        "Style: IntroTitle,Arial-BoldMT,48,&H00FFFFFF,&H00000000,&H80000000,-1,1,2,40,40,30",
        "Style: IntroSub,Arial,32,&H00BBBBBB,&H00000000,&H80000000,0,1,2,40,40,30",
        "Style: IntroBrand,Arial-BoldMT,24,&H00FFD700,&H00000000,&H00000000,0,1,2,40,40,30",
        "Style: Comm,Arial-BoldMT,38,&H00FFFFFF,&H00000000,&H80000000,-1,1,2,40,40,30",
        "Style: Sub,Arial,24,&H00888888,&H00000000,&H00000000,0,1,2,40,40,10",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Text",
    ]

    # ── intro card (well below video) ──
    pad = "{\\fad(15,15)}"
    iy = safe_zone + 80
    if movie_label:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{intro_end},IntroTitle,"
            f"{pad}{{\\pos({cx},{iy})}}{movie_label}"
        )
        iy += 65
    if scene_label:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{intro_end},IntroSub,"
            f"{pad}{{\\pos({cx},{iy})}}{scene_label}"
        )
        iy += 55
    lines.append(
        f"Dialogue: 0,0:00:00.00,{intro_end},IntroBrand,"
        f"{pad}{{\\pos({cx},{iy})}}BEHIND THE SCENE"
    )

    # ── persistent footer at very bottom ──
    footer_text = f"{movie_label} — {scene_label}" if scene_label else (movie_label or "")
    if footer_text:
        lines.append(
            f"Dialogue: 0,{intro_end},{full_end},Sub,"
            f"{{\\pos({cx},{H - 50})}}{footer_text}"
        )

    # ── collect commentary with original timing ──
    raw = [s for s in segments if s.get("commentary")]
    raw_uniq = []
    seen_texts = set()
    for s in raw:
        sig = s["commentary"].lower()[:40]
        if sig not in seen_texts:
            seen_texts.add(sig)
            raw_uniq.append(s)

    best = critic.pick_best([s["commentary"] for s in raw_uniq], PHASE_COUNT)
    best_set = set(best)

    events = []
    for s in raw_uniq:
        if s["commentary"] not in best_set:
            continue
        start = max(s["start"], intro_end_t + 0.5)
        word_count = len(s["commentary"].split())
        read_time = max(MIN_SECONDS, word_count / 3.3)
        min_end = start + read_time
        events.append({
            "start": start,
            "end": s["end"],
            "min_end": min_end,
            "text": s["commentary"],
        })

    events.sort(key=lambda e: e["start"])

    # ── timing: extend for readability, cap to avoid overlap ──
    fade_s = FADE_CS / 100.0
    for i, ev in enumerate(events):
        adj = max(ev["end"], ev["min_end"])
        if i < len(events) - 1:
            adj = min(adj, events[i + 1]["start"] - fade_s)
        else:
            adj = min(adj, duration)
        adj = max(adj, ev["start"] + fade_s + 0.5)
        ev["end"] = adj

    # ── write commentary events (centered, just below max video zone) ──
    comm_y = safe_zone + COMM_Y_OFFSET
    fade_tag = f"{{\\fad({FADE_CS},{FADE_CS})}}"
    for ev in events:
        start = _fmt_ts(ev["start"])
        end = _fmt_ts(ev["end"])
        wrapped = _wrap(ev["text"])
        if not wrapped:
            continue
        lines.append(
            f"Dialogue: 0,{start},{end},Comm,"
            f"{fade_tag}{{\\pos({cx},{comm_y})}}{_esc(wrapped)}"
        )

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def compose(
    video_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    target_width: int = 1080,
    target_height: int = 1920,
):
    vid_h = int(target_height * VIDEO_HEIGHT_RATIO)
    subprocess.run(
        [
            "ffmpeg",
            "-i", str(video_path),
            "-vf",
            f"scale={target_width}:{vid_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:0:{PAD_TOP}:color=#1a1a1a,"
            f"drawbox=0:0:{target_width}:{PAD_TOP}:color=black@1:t=fill,"
            f"ass={ass_path}",
            "-c:a", "aac", "-b:a", "128k",
            "-preset", "fast", "-crf", "23",
            "-y", str(output_path),
        ],
        capture_output=True, text=True, check=True,
    )
