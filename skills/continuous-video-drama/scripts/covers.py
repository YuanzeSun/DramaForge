"""Export exact PNG crops from GPT Image cover artwork; never generate or redraw art."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
import imageio_ffmpeg

from workflow import file_hash, identifier, write


def export_cover(source, out, aspect="4:3", crop=None, *, overwrite=False, record=None, episode=None):
    source = Path(source).resolve()
    out = Path(out).resolve()
    record = Path(record).resolve() if record else out.with_suffix(".cover.json")
    if episode is not None:
        identifier(episode)
    try:
        ratio = tuple(int(n) for n in aspect.split(":"))
    except ValueError as exc:
        raise ValueError("aspect must be positive width:height integers") from exc
    if len(ratio) != 2 or min(ratio) <= 0:
        raise ValueError("aspect must be positive width:height integers")
    if len({source, out, record}) != 3:
        raise ValueError("source, output and provenance record must be different files")
    if out.suffix.lower() != ".png":
        raise ValueError("cover output must be PNG for lossless crop verification")
    if not overwrite and (out.exists() or record.exists()):
        raise ValueError("output or provenance already exists; use --overwrite for an authorized replacement")
    with Image.open(source) as im:
        if im.format != "PNG" or im.mode not in {"RGB", "RGBA"}:
            raise ValueError("source must be an RGB/RGBA PNG saved from the image tool")
        original = im.copy()
    width, height = original.size
    num, den = ratio
    if crop is None:
        k = min(width // num, height // den)
        cw, ch = num * k, den * k
        x, y = (width - cw) // 2, (height - ch) // 2
    else:
        if len(crop) != 4 or any(type(n) is not int for n in crop):
            raise ValueError("crop must contain integer X Y WIDTH HEIGHT")
        x, y, cw, ch = crop
    if min(x, y) < 0 or min(cw, ch) <= 0 or x + cw > width or y + ch > height:
        raise ValueError("crop falls outside the source image")
    if cw * den != ch * num:
        raise ValueError("crop dimensions do not match the requested aspect")
    source_hash = file_hash(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{out.stem}.", suffix=".png", dir=out.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        result = subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vf", f"crop={cw}:{ch}:{x}:{y}:exact=1", "-frames:v", "1",
            "-c:v", "png", "-pix_fmt", "rgba" if original.mode == "RGBA" else "rgb24",
            "-update", "1", str(temporary)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"FFmpeg cover crop failed: {result.stderr.strip()}")
        with Image.open(temporary) as exported:
            expected = original.crop((x, y, x + cw, y + ch))
            if exported.mode != expected.mode or exported.size != expected.size or exported.tobytes() != expected.tobytes():
                raise RuntimeError("exported cover pixels differ from the source crop")
        if file_hash(source) != source_hash:
            raise RuntimeError("source image changed during export")
        data = {
            "source": str(source), "source_sha256": source_hash, "source_size": [width, height],
            "output": str(out), "output_sha256": file_hash(temporary), "size": [cw, ch],
            "aspect": aspect, "crop_xywh": [x, y, cw, ch],
            "pixel_identical_to_source_region": True, "resized": False, "text_relaid": False,
        }
        if episode is not None:
            data["episode"] = episode
        temporary.replace(out)
        write(record, data)
        return data
    finally:
        temporary.unlink(missing_ok=True)


def add_arguments(parser):
    parser.add_argument("--source", required=True, help="durable GPT Image PNG mother artwork")
    parser.add_argument("--out", required=True, help="one final PNG cover, with no text redrawing")
    parser.add_argument("--aspect", default="4:3", help="exact width:height ratio; default 4:3")
    parser.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    parser.add_argument("--record", help="JSON crop provenance path; default next to the PNG")
    parser.add_argument("--episode", help="optional episode identifier to record")
    parser.add_argument("--overwrite", action="store_true", help="replace a user-authorized current cover")


def run(args):
    data = export_cover(args.source, args.out, args.aspect, args.crop,
                        overwrite=args.overwrite, record=args.record, episode=args.episode)
    print(f"COVER {data['output']} {data['size'][0]}x{data['size'][1]} {data['aspect']} PIXELS VERIFIED")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    try:
        return run(parser.parse_args(argv))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
