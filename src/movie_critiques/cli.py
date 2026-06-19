import csv
import sys
from pathlib import Path

import click

from . import downloader, transcriber, segmenter, critic, compositor

SCENES_CSV = Path(__file__).resolve().parents[2] / "scenes.csv"
WORK_BASE = Path(__file__).resolve().parents[2] / "work"


def _read_scene(rank: int) -> dict:
    with open(SCENES_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["rank"]) == rank:
                return row
    raise click.ClickException(f"Scene #{rank} not found in scenes.csv")


def _update_status(rank: int, status: str):
    rows = []
    with open(SCENES_CSV, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if int(row["rank"]) == rank:
                row["status"] = status
            rows.append(row)
    with open(SCENES_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text).strip("_").lower()


def _scene_dir(rank: int, row: dict) -> Path:
    slug = _slug(f"{rank:02d}_{row['movie']}_{row['year']}")
    return WORK_BASE / slug


@click.group()
def cli():
    pass


@cli.command()
@click.option("--scene", type=int, required=True, help="Scene rank from scenes.csv")
@click.option("--duration", type=float, default=60.0, help="Target segment duration (seconds)")
@click.option("--output", default=None, help="Output video path (default: work/<scene>/output.mp4)")
@click.option("--force", is_flag=True, help="Re-download and re-process even if cached")
def make(scene, duration, output, force):
    row = _read_scene(scene)
    movie = row["movie"]
    year = row["year"]
    scene_desc = row["scene"]
    search_query = row["youtube_search"]
    key_line = row["key_line"]

    click.echo(f"Scene {scene}: {movie} — {scene_desc}")
    click.echo(f"  YouTube search: {search_query}")
    click.echo(f"  Key line: {key_line}")
    click.echo(f"  Target duration: {duration}s")

    work_dir = _scene_dir(scene, row)
    work_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"  Work dir: {work_dir}")

    clip_path = work_dir / "download.mp4"
    seg_path = work_dir / "segment.mp4"
    ass_path = work_dir / "commentary.ass"
    if output is None:
        output = str(work_dir / "output.mp4")

    all_cached = all(p.exists() for p in [clip_path, seg_path, ass_path, Path(output)])
    if all_cached and not force:
        click.echo(f"  All cached files exist. Use --force to regenerate.")
        return

    if clip_path.exists() and not force:
        click.echo(f"  Using cached download ({clip_path})")
    else:
        click.echo("  Searching YouTube...")
        entries = downloader.search_youtube(search_query)
        best = downloader.pick_best(entries)
        if best is None:
            click.echo("    Trying search with key line included...")
            entries = downloader.search_youtube(f"{search_query} {key_line}")
            best = downloader.pick_best(entries)
        if best is None:
            raise click.ClickException("No suitable clip found on YouTube")
        click.echo(f"    Picked: {best.get('title', '?')} "
                   f"({best.get('duration', '?')}s, {best.get('view_count', '?')} views)")
        click.echo("  Downloading...")
        downloaded = downloader.download(best["webpage_url"] or best["id"], work_dir)
        if downloaded != clip_path:
            downloaded.rename(clip_path)
        click.echo(f"    Saved: {clip_path}")

    click.echo("  Transcribing with whisper...")
    segments = transcriber.transcribe(clip_path)
    click.echo(f"    {len(segments)} segments found")

    match = segmenter.find_best_segment(segments, key_line)
    if match is None:
        longest = segmenter.find_richest_segment(segments)
        if longest:
            click.echo(f"    Key line not found. Using richest segment.")
            seg_start, seg_end = longest
        else:
            raise click.ClickException(
                f"Key line not found in transcript.\n" +
                "\n".join(f"    [{s['start']:.1f}s-{s['end']:.1f}s] {s['text'].strip()}" for s in segments)
            )
    else:
        seg_start, seg_end = match
    click.echo(f"    Center segment: {seg_start:.1f}s — {seg_end:.1f}s")

    mid = (seg_start + seg_end) / 2
    half = duration / 2
    cut_start = max(0, mid - half)
    cut_end = cut_start + duration

    click.echo(f"  Extracting segment {cut_start:.1f}s — {cut_end:.1f}s...")
    segmenter.cut_segment(clip_path, cut_start, cut_end, seg_path)

    click.echo("  Transcribing segment...")
    seg_segments = transcriber.transcribe(seg_path)
    click.echo(f"    {len(seg_segments)} raw segments")

    merged = segmenter.merge_segments(seg_segments)
    click.echo(f"    merged into {len(merged)} blocks")

    click.echo("  Searching for commentary...")
    enriched = critic.batch_commentary(movie, merged)
    commentary_found = sum(1 for e in enriched if e.get("commentary"))
    click.echo(f"    {commentary_found} timed commentary items found:")
    for e in enriched:
        if e.get("commentary"):
            ts = f"[{e['start']:.1f}s-{e['end']:.1f}s]"
            click.echo(f"    {ts} {e['commentary']}")

    click.echo("  Generating overlay text...")
    movie_label = f"{movie} ({year})"
    compositor.generate_ass(enriched, ass_path, duration=duration, movie_label=movie_label, scene_label=scene_desc)

    click.echo(f"  Composing final video → {output}...")
    compositor.compose(seg_path, ass_path, output)
    click.echo(f"  Done! Output: {output}")

    _update_status(scene, "completed")
    click.echo("  Updated scenes.csv status → completed")


@cli.command()
@click.option("--scene", type=int, required=True, help="Scene rank from scenes.csv")
def status(scene):
    row = _read_scene(scene)
    work_dir = _scene_dir(scene, row)
    click.echo(f"Scene {scene}: {row['movie']} — {row['scene']}")
    click.echo(f"  CSV status: {row['status']}")
    click.echo(f"  Work dir: {work_dir}")
    for fname in ["download.mp4", "segment.mp4", "commentary.ass", "output.mp4"]:
        fp = work_dir / fname
        if fp.exists():
            size = fp.stat().st_size
            click.echo(f"    {fname}: {size / 1024 / 1024:.1f} MB")
        else:
            click.echo(f"    {fname}: not found")


if __name__ == "__main__":
    cli()
