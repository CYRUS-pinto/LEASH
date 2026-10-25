import asyncio
import os
import sys
import time
import subprocess
from playwright.async_api import async_playwright

async def render_film(
    stage_file="stage_89s.html",
    audio_file="audio/final_master_audio_89s.m4a",
    out_file="dist/CAROT_LEASH_Launch_89s.mp4",
    duration=89.0,
    fps=60,
    width=1920,
    height=1080,
    scale_4k=True
):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    stage_path = f"file:///{os.path.join(base_dir, stage_file).replace('\\', '/')}"
    audio_path = os.path.join(base_dir, audio_file)
    out_path = os.path.join(base_dir, out_file)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    log_path = os.path.join(base_dir, "ffmpeg_render.log")

    total_frames = int(duration * fps)
    print(f"=== CAROT LEASH Video Rendering Engine ===", flush=True)
    print(f"Stage: {stage_file}", flush=True)
    print(f"Duration: {duration:.2f}s | FPS: {fps} | Total Frames: {total_frames}", flush=True)
    print(f"Resolution: {'3840x2160 (4K UHD)' if scale_4k else f'{width}x{height}'}", flush=True)
    print(f"Audio Track: {audio_file}", flush=True)
    print(f"Target Output: {out_path}", flush=True)

    # Build FFmpeg command
    vf_filters = []
    if scale_4k:
        vf_filters.append("scale=3840:2160:flags=lanczos")
    vf_filters.append("format=yuv420p")
    vf_str = ",".join(vf_filters)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-framerate", str(fps),
        "-i", "-",  # Pipe from stdin
        "-i", audio_path,
        "-vf", vf_str,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        out_path
    ]

    print("Starting FFmpeg encoder process...", flush=True)
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=log_file,
        stderr=subprocess.STDOUT
    )

    print("Launching Chromium headless renderer...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(stage_path, wait_until="networkidle")
        await page.wait_for_timeout(600)

        t_start = time.time()
        for f in range(total_frames):
            t_sec = f / float(fps)
            await page.evaluate(f"window.seek({t_sec});")
            jpeg_bytes = await page.screenshot(type="jpeg", quality=90)
            try:
                proc.stdin.write(jpeg_bytes)
            except BrokenPipeError:
                print("FFmpeg process closed early.", flush=True)
                break

            if (f + 1) % 120 == 0 or (f + 1) == total_frames:
                elapsed = time.time() - t_start
                cur_fps = (f + 1) / elapsed
                pct = ((f + 1) / total_frames) * 100
                rem_frames = total_frames - (f + 1)
                rem_time = rem_frames / cur_fps if cur_fps > 0 else 0
                print(f"Frame {f+1}/{total_frames} ({pct:5.1f}%) | {cur_fps:4.1f} fps | Elapsed: {elapsed:5.1f}s | ETA: {rem_time:5.1f}s", flush=True)

        proc.stdin.close()
        proc.wait()
        log_file.close()
        await browser.close()

    if proc.returncode != 0:
        with open(log_path, "r", encoding="utf-8") as lf:
            err = lf.read()
        print(f"FFmpeg error:\n{err}", flush=True)
        raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")

    print(f"\nSUCCESS: Render completed in {time.time() - t_start:.2f}s!", flush=True)
    print(f"Rendered file size: {os.path.getsize(out_path) / (1024*1024):.2f} MB", flush=True)
    print(f"Output: {out_path}", flush=True)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Render only first 5 seconds for rapid testing")
    parser.add_argument("--stage", default="stage_89s.html")
    parser.add_argument("--audio", default="audio/final_master_audio_89s.m4a")
    parser.add_argument("--output", default="dist/CAROT_LEASH_Launch_89s.mp4")
    parser.add_argument("--duration", type=float, default=89.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--no-4k", action="store_true")
    args = parser.parse_args()

    dur = 5.0 if args.test else args.duration
    out = args.output.replace(".mp4", "_test.mp4") if args.test else args.output
    asyncio.run(render_film(
        stage_file=args.stage,
        audio_file=args.audio,
        out_file=out,
        duration=dur,
        fps=args.fps,
        scale_4k=not args.no_4k
    ))
