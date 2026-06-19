import subprocess
import textwrap
from pathlib import Path

from . import critic

PHASE_COUNT = 6
PHASE_PAD = 1.0
FADE_CS = 25
WRAP_CHARS = 40


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
    movie_btm = int(H * 0.62)
    intro_end_t = min(5.0, duration)

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
        "Style: WM,Arial-BoldMT,22,&H80FFFFFF,&H00000000,&H00000000,0,1,1,20,20,10",
        "Style: SceneLabel,Arial,26,&H00AAAAAA,&H00000000,&H00000000,0,1,2,80,80,30",
        "Style: IntroTitle,Arial-BoldMT,48,&H00FFFFFF,&H00000000,&H80000000,-1,1,1,80,80,30",
        "Style: IntroSub,Arial,32,&H00BBBBBB,&H00000000,&H80000000,0,1,1,80,80,30",
        "Style: IntroBrand,Arial-BoldMT,24,&H00FFD700,&H00000000,&H00000000,0,1,1,80,80,30",
        "Style: Comm,Arial-BoldMT,40,&H00FFFFFF,&H00000000,&H80000000,-1,1,1,80,80,30",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Text",
    ]

    full_end = _fmt_ts(duration)
    intro_end = _fmt_ts(intro_end_t)
    pad = "{\\fad(15,15)}"

    # ── top-left watermark (entire video) ──
    if movie_label:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{full_end},WM,,"
            f"{{\\pos(40,45)}}{movie_label}"
        )

    # ── scene label at top of bottom panel (appears after intro) ──
    label_text = f"{movie_label} — {scene_label}" if scene_label else (movie_label or "")
    if label_text:
        lines.append(
            f"Dialogue: 0,{intro_end},{full_end},SceneLabel,,"
            f"{{\\pos({W//2},{movie_btm + 35})}}{label_text}"
        )

    # ── intro card ──
    iy = movie_btm + 150
    if movie_label:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{intro_end},IntroTitle,,"
            f"{pad}{{\\pos(80,{iy})}}{movie_label}"
        )
        iy += 65
    if scene_label:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{intro_end},IntroSub,,"
            f"{pad}{{\\pos(80,{iy})}}{scene_label}"
        )
        iy += 55
    lines.append(
        f"Dialogue: 0,0:00:00.00,{intro_end},IntroBrand,,"
        f"{pad}{{\\pos(80,{iy})}}BEHIND THE SCENE"
    )

    # ── collect & phase commentary ──
    raw = _uniq([s["commentary"] for s in segments if s.get("commentary")])
    best = critic.pick_best(raw, PHASE_COUNT)

    if not best:
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        return

    phase_dur = (duration - intro_end_t) / len(best)
    fade_s = FADE_CS / 100.0
    comm_y = H - 120
    fade_tag = f"{{\\fad({FADE_CS},{FADE_CS})}}"

    for i, text in enumerate(best):
        start_t = intro_end_t + i * phase_dur
        end_t = start_t + phase_dur - PHASE_PAD
        if i == len(best) - 1:
            end_t = duration
        if end_t <= start_t + fade_s:
            end_t = start_t + fade_s
        start = _fmt_ts(start_t)
        end = _fmt_ts(end_t)
        wrapped = _wrap(text)
        if not wrapped:
            continue
        lines.append(
            f"Dialogue: 0,{start},{end},Comm,,"
            f"{fade_tag}{{\\pos(80,{comm_y})}}{_esc(wrapped)}"
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
    subprocess.run(
        [
            "ffmpeg",
            "-i", str(video_path),
            "-vf",
            f"scale={target_width}:{int(target_height*0.62)}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:0:0:color=#1a1a1a,"
            f"ass={ass_path}",
            "-c:a", "aac", "-b:a", "128k",
            "-preset", "fast", "-crf", "23",
            "-y", str(output_path),
        ],
        capture_output=True, text=True, check=True,
    )
