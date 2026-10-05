"""Generate the anime character sheet from temp_prompt.txt + a reference photo via Gemini.

Run: python generate_sheet.py [photo_path] [output_path]
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-image"
ROOT = Path(__file__).resolve().parent


def main():
    load_dotenv(ROOT.parent / ".env")
    photo = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "input_photos" / "photo.jpg"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "character_sheet.png"
    prompt = (ROOT / "prompts" / "character_sheet_prompt.txt").read_text(encoding="utf-8")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    mime = "image/png" if photo.suffix.lower() == ".png" else "image/jpeg"
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=photo.read_bytes(), mime_type=mime), prompt],
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    for part in resp.candidates[0].content.parts:
        if part.inline_data:
            out.write_bytes(part.inline_data.data)
            print(f"saved {out}")
            return
        if part.text:
            print(part.text)
    sys.exit("no image returned")


if __name__ == "__main__":
    main()
