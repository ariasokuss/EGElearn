"""OCR images via Mistral and output markdown.

Usage:
    uv run python scripts/ocr_images.py image1.jpg image2.png
    uv run python scripts/ocr_images.py --save image1.jpg   # writes image1.md
"""

import argparse
import asyncio
import base64
import mimetypes
import sys
from pathlib import Path

from mistralai.client import Mistral

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_key(key: str) -> str:
    """Read a key from backend/.env without pulling in dotenv."""
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} not found in {ENV_FILE}")


def encode_image(path: Path) -> tuple[str, str]:
    """Return (base64_data, mime_type) for an image file."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return data, mime


async def ocr_image(client: Mistral, model: str, path: Path) -> str:
    b64, mime = encode_image(path)
    response = await client.ocr.process_async(
        model=model,
        document={
            "type": "image_url",
            "image_url": f"data:{mime};base64,{b64}",
        },
        include_image_base64=False,
    )
    parts: list[str] = []
    for page in response.pages:
        content = (page.markdown or "").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts)


async def main(paths: list[Path], save: bool) -> None:
    api_key = load_env_key("MISTRAL__API_KEY")
    model = "mistral-ocr-latest"
    client = Mistral(api_key=api_key)

    for path in paths:
        if not path.exists():
            print(f"[skip] {path} does not exist", file=sys.stderr)
            continue
        print(f"[ocr] {path.name} ...", file=sys.stderr)
        md = await ocr_image(client, model, path)
        if save:
            out = path.with_suffix(".md")
            out.write_text(md + "\n", encoding="utf-8")
            print(f"[saved] {out}", file=sys.stderr)
        else:
            print(f"--- {path.name} ---")
            print(md)
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR images via Mistral")
    parser.add_argument("images", nargs="+", type=Path, help="Image files to process")
    parser.add_argument(
        "--save", action="store_true", help="Save as .md files instead of printing"
    )
    args = parser.parse_args()
    asyncio.run(main(args.images, args.save))
