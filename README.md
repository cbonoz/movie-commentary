# movie-critiques

Generate TikTok-style vertical videos (9:16) with movie scene clips and timed commentary overlays.

## How it works

```
YouTube URL → yt-dlp (download) → ffmpeg (segment) → mlx-whisper (transcribe)
  → Web search commentary → ffmpeg composite (9:16, stacked) → output.mp4
```

## Requirements

- macOS with Apple Silicon (for mlx-whisper)
- ffmpeg (`brew install ffmpeg`)
- uv (`brew install uv`)

## Setup

```bash
uv sync
```

## Usage

```bash
# Run scene N from scenes.csv
uv run movie-critique make --scene 1

# Run with specific duration and force rebuild
uv run movie-critique make --scene 2 --duration 90 --force

# Check cache status for a scene
uv run movie-critique status --scene 1
```

## Output

Each scene's files are cached in `work/{rank}_{movie}_{year}/`:

| File | Description |
|---|---|
| `download.mp4` | Original YouTube clip |
| `segment.mp4` | Extracted 60s segment |
| `commentary.ass` | Timed subtitle overlay |
| `output.mp4` | Final 9:16 TikTok video |

## Scenes

`scenes.csv` ranks 40 iconic film scenes by priority. Columns:

```
rank,movie,year,scene,key_line,themes,youtube_search,status
```

Set `status` to `completed` manually after reviewing a scene.

## Commands

| Command | Description |
|---|---|
| `make --scene N [--duration S] [--force]` | Generate a scene video |
| `status --scene N` | Check cached files for a scene |
