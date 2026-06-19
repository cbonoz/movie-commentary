from pathlib import Path

import mlx_whisper

MODEL = "mlx-community/whisper-small-mlx"


def transcribe(audio_path: str | Path) -> list[dict]:
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=MODEL,
        word_timestamps=True,
    )
    return result["segments"]
