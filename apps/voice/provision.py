"""Install the pinned bilingual voice assets in the station model directory."""

import argparse
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen


UPSTREAM = "https://huggingface.co/rhasspy/piper-voices/resolve"
VOICES = {
    "en": (
        "e9c8a39444359388adaa94255becb37a5a2b8e51",
        "en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx",
        ((63531379, "6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22"),
         (4972, "141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860")),
    ),
    "fa": (
        "929396f9d01ab9078f9c29ef519c25d9d4940258",
        "fa/fa_IR/ganji/medium/epoch=5719-step=2609600-ganji.onnx",
        ((63516050, "6a98504bb77dc2fd3a863c977d37e67a6a525fdf661917385d569a3ff78e6cae"),
         (7089, "315a65d95460c146fe6ab02c6f8251b13dcac28d23140fce5999b57866931b49")),
    ),
}


def verify(path: Path, size: int, digest: str) -> None:
    if path.stat().st_size != size:
        raise ValueError(f"Unexpected size for {path.name}")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError(f"SHA-256 mismatch for {path.name}")


def install(target: Path, url: str, size: int, digest: str) -> None:
    if target.exists():
        verify(target, size, digest)
        return
    part = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix="voice-", delete=False) as stream:
            part = Path(stream.name)
            remaining = size
            with urlopen(url, timeout=30) as response:
                while data := response.read(min(remaining + 1, 1024 * 1024)):
                    remaining -= len(data)
                    if remaining < 0:
                        raise ValueError(f"Download exceeds pinned size for {target.name}")
                    stream.write(data)
        verify(part, size, digest)
        part.chmod(0o644)
        try:
            os.link(part, target)
        except FileExistsError:
            verify(target, size, digest)
    finally:
        if part is not None:
            part.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=os.getenv("AI_STATION_DATA", "/srv/ai-station"))
    args = parser.parse_args()
    directory = args.data_root / "models/voice/piper"
    directory.mkdir(parents=True, exist_ok=True)
    for language, (revision, remote, assets) in VOICES.items():
        for suffix, (size, digest) in zip(("", ".json"), assets):
            target = directory / f"{language}.onnx{suffix}"
            install(target, f"{UPSTREAM}/{revision}/{remote}{suffix}", size, digest)
        print(f"Verified local voice: {language}")


if __name__ == "__main__":
    main()
