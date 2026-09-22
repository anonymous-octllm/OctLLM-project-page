#!/usr/bin/env python3
"""Build the captioned, 60-second project-page octree film.

Install Pillow and imageio-ffmpeg, or provide an installed FFmpeg with --ffmpeg.
From the project-page checkout:

    python scripts/build_generation_film.py
    python scripts/build_generation_film.py --frames-root /path/to/OctLLM/outputs/octllm_animation

The default uses the three original project-page MP4s. --frames-root uses the
original lossless Blender PNG sequences instead. Add --webm for a VP9 alternate.
The labels follow scripts/visualization/build_octree_animation.py in the research
checkout, whose timeline uses 1-based frames at 24 fps. This is an illustrative
replay constructed from source GLBs; it does not record model inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

FPS = 24
CLIP_FRAMES = 480
WIDTH, HEIGHT = 1920, 1080
CLIPS = ("robot", "airplane", "truck")
CAPTION_FONT_PIXELS = 50
CAPTION_TOP_PIXELS = 64
CAPTION_BAND_TOP_PIXELS = 48
# Half-open intervals in Blender's original, 1-based frame numbering.
PHASES = (
    (22, 98, "Depth 3 generating"),
    (98, 174, "Depth 4 generating"),
    (174, 252, "Depth 5 generating"),
    (252, 330, "Depth 6 generating"),
    (330, 382, "Voxel completing"),
    (382, 425, "Surface reveal"),
    (425, 481, "Final asset"),
)


def mp4_metadata(path: Path) -> dict:
    """Read movie duration and track dimensions independently of encoder flags."""
    raw = path.read_bytes()
    result = {}

    def boxes(start, end):
        cursor = start
        while cursor + 8 <= end:
            size, kind = struct.unpack_from(">I4s", raw, cursor)
            header = 8
            if size == 1:
                size = struct.unpack_from(">Q", raw, cursor + 8)[0]
                header = 16
            elif size == 0:
                size = end - cursor
            if size < header or cursor + size > end:
                raise ValueError(f"Invalid MP4 box in {path}")
            body = cursor + header
            if kind in (b"moov", b"trak"):
                boxes(body, cursor + size)
            elif kind == b"mvhd":
                version = raw[body]
                offset = body + (20 if version == 1 else 12)
                timescale = struct.unpack_from(">I", raw, offset)[0]
                duration = struct.unpack_from(">Q" if version == 1 else ">I", raw, offset + 4)[0]
                result["duration_seconds"] = duration / timescale
            elif kind == b"tkhd":
                width, height = struct.unpack_from(">II", raw, cursor + size - 8)
                if width and height:
                    result.update(width=width // 65536, height=height // 65536)
            cursor += size

    boxes(0, len(raw))
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_font(override):
    if override:
        return override
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit("Pass --font with a local sans-serif TTF/OTF font.")


def make_labels(folder, font_path):
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(font_path), CAPTION_FONT_PIXELS)
    masks = {}
    for _, _, text in PHASES:
        mask = Image.new("RGBA", (WIDTH, 144))
        ImageDraw.Draw(mask).text(
            (WIDTH / 2, CAPTION_TOP_PIXELS - CAPTION_BAND_TOP_PIXELS),
            text, font=font, fill="#263835", anchor="mt",
        )
        masks[text] = mask
    blank = Image.new("RGBA", (WIDTH, 144))
    cache = {}
    for index in range(CLIP_FRAMES * len(CLIPS)):
        frame = index % CLIP_FRAMES + 1
        text, opacity = "", 0
        for start, end, label in PHASES:
            if start <= frame < end:
                # Five-frame fades keep stage changes quiet; the last label
                # follows the source film's existing twelve-frame end fade.
                fade_out = 12 if end == 481 else 5
                progress = max(0, min(1, (frame - start) / 5, (end - 1 - frame) / fade_out))
                opacity = round(255 * progress * progress * (3 - 2 * progress))
                text = label
                break
        key = (text, opacity)
        if key not in cache:
            label_file = folder / f"caption_{len(cache):03d}.png"
            rendered = masks[text].copy() if text else blank.copy()
            if text:
                rendered.putalpha(rendered.getchannel("A").point(lambda alpha: round(alpha * opacity / 255)))
            rendered.save(label_file)
            cache[key] = label_file
        (folder / f"frame_{index + 1:04d}.png").symlink_to(cache[key].name)


def run(command):
    subprocess.run([str(part) for part in command], check=True)


def decode_check(ffmpeg, path, threads):
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-threads", str(threads),
         "-i", str(path), "-map", "0:v:0", "-threads", str(threads),
         "-progress", "pipe:1", "-nostats", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    frames = [int(line.split("=", 1)[1]) for line in result.stdout.splitlines() if line.startswith("frame=")]
    if not frames or frames[-1] != CLIP_FRAMES * len(CLIPS):
        raise ValueError(f"Unexpected decoded frame count for {path}: {frames[-1:]}")
    return {"full_decode_passed": True, "decoded_frames": frames[-1]}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frames-root", type=Path)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--crf", type=int, default=19)
    parser.add_argument("--webm", action="store_true")
    args = parser.parse_args()
    if args.threads < 1 or not 0 <= args.crf <= 51:
        parser.error("--threads must be positive and --crf must be in [0, 51]")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    font = find_font(args.font)
    from PIL import Image

    video_dir = root / "assets/videos"
    mp4 = video_dir / "generation.mp4"
    poster = root / "assets/images/generation-poster.webp"
    video_dir.mkdir(parents=True, exist_ok=True)
    poster.parent.mkdir(parents=True, exist_ok=True)
    sources = []
    inputs = []
    for clip in CLIPS:
        inputs += ["-threads", args.threads]
        source = {"asset": clip, "source_glb": f"assets/examples/understanding/{clip}.glb"}
        if args.frames_root:
            folder = args.frames_root.resolve() / clip
            frames = sorted((folder / "frames").glob("frame_*.png"))
            expected = [f"frame_{number:04d}.png" for number in range(1, CLIP_FRAMES + 1)]
            if [frame.name for frame in frames] != expected:
                raise ValueError(f"Expected exactly 480 consecutive PNGs in {folder / 'frames'}")
            for frame in frames:
                with Image.open(frame) as image:
                    if image.size != (WIDTH, HEIGHT):
                        raise ValueError(f"Incorrect dimensions: {frame}")
            inputs += ["-framerate", FPS, "-start_number", 1, "-i", folder / "frames/frame_%04d.png"]
            manifest = folder / "frames/render_manifest.json"
            source.update(input=f"outputs/octllm_animation/{clip}/frames/frame_%04d.png", format="lossless PNG sequence")
            if manifest.exists():
                source["scene_sha256"] = json.loads(manifest.read_text())["scene_sha256"]
        else:
            path = video_dir / f"{clip}.mp4"
            if mp4_metadata(path) != {"duration_seconds": 20.0, "width": WIDTH, "height": HEIGHT}:
                raise ValueError(f"Expected a 20-second 1920x1080 source: {path}")
            inputs += ["-i", path]
            source.update(input=str(path.relative_to(root)), format="H.264 MP4", sha256=digest(path))
        sources.append(source)

    with tempfile.TemporaryDirectory(prefix="octllm-generation-film-") as temporary:
        temp = Path(temporary)
        make_labels(temp, font)
        inputs += ["-threads", args.threads, "-framerate", FPS, "-start_number", 1, "-i", temp / "frame_%04d.png"]
        stages = [f"[{index}:v]setpts=PTS-STARTPTS,format=rgba[clip{index}]" for index in range(3)]
        stages += ["[clip0][clip1][clip2]concat=n=3:v=1:a=0[joined]",
                   f"[joined][3:v]overlay=x=0:y={CAPTION_BAND_TOP_PIXELS}:shortest=1:format=rgb,"
                   "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p[film]"]
        common = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", args.threads]
        common += inputs + ["-filter_complex", ";".join(stages), "-map", "[film]", "-an",
                            "-threads", args.threads, "-r", FPS, "-fps_mode", "cfr",
                            "-color_range", "tv", "-color_primaries", "bt709",
                            "-color_trc", "bt709", "-colorspace", "bt709"]
        print("Encoding 3 × 480 frames with synchronized phase captions...", flush=True)
        run(common + ["-c:v", "libx264", "-preset", "medium", "-crf", args.crf,
                      "-movflags", "+faststart", mp4])
        exports = [mp4]
        if args.webm:
            webm = video_dir / "generation.webm"
            run(common + ["-c:v", "libvpx-vp9", "-b:v", 0, "-crf", 29,
                          "-row-mt", 1, "-cpu-used", 4, webm])
            exports.append(webm)
        snapshot = temp / "poster.png"
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-threads", args.threads,
             "-i", mp4, "-vf", "select=eq(n\\,287)", "-frames:v", 1, snapshot])
        with Image.open(snapshot) as image:
            image.save(poster, "WEBP", quality=90, method=6)

    metadata = mp4_metadata(mp4)
    if metadata != {"duration_seconds": 60.0, "width": WIDTH, "height": HEIGHT}:
        raise ValueError(f"Unexpected encoded video metadata: {metadata}")
    verified = {}
    for path in exports:
        print(f"Fully decoding {path.name}...", flush=True)
        verified[path.name] = {**decode_check(ffmpeg, path, args.threads),
                               "bytes": path.stat().st_size, "sha256": digest(path)}
    report = {
        "description": "Three sequential source-GLB octree visualizations with phase captions.",
        "provenance": "Illustrative replay built from existing GLBs, not a model-inference recording. "
                      "Completion restores the source surface octree; the final surface is the original GLB.",
        "timing_source": "scripts/visualization/build_octree_animation.py on the research branch",
        "fps": FPS, "frames": CLIP_FRAMES * len(CLIPS), **metadata,
        "order": list(CLIPS), "sources": sources,
        "phase_timing": [{"label": text, "source_frame_start": start, "source_frame_end_inclusive": end - 1,
                          "clip_seconds_start": (start - 1) / FPS, "clip_seconds_end": (end - 1) / FPS}
                         for start, end, text in PHASES],
        "clip_seconds_start": [0, 20, 40],
        "caption_font": font.name, "caption_font_pixels": CAPTION_FONT_PIXELS,
        "caption_font_sha256": digest(font),
        "caption_alignment": "top center",
        "caption_anchor_pixels": {"x": WIDTH / 2, "y": CAPTION_TOP_PIXELS},
        "caption_text_anchor": "mt",
        "poster_frame_zero_based": 287,
        "verification": verified,
    }
    (video_dir / "generation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"mp4": str(mp4), "poster": str(poster), **metadata, "verification": verified}, indent=2))


if __name__ == "__main__":
    main()
