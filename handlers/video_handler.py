import os
import asyncio
import shlex
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

VIDEO_DIR = os.getenv("VIDEO_DIR", "/tmp/nori_videos")
DEFAULT_COVER = os.getenv("DEFAULT_COVER_PATH", "")  # 任意のデフォルト画像
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()


def _ensure_dir():
    os.makedirs(VIDEO_DIR, exist_ok=True)


def _generate_placeholder_cover(title: str, dest: str, size=(1280, 720)) -> str:
    """SUNOのカバー画像が無いとき用のフォールバック。タイトルを焼き込む"""
    img = Image.new("RGB", size, color=(20, 24, 40))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 64)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), title, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((size[0] - w) / 2, (size[1] - h) / 2), title, fill=(240, 240, 255), font=font)
    img.save(dest, "PNG")
    return dest


async def _run(cmd: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


async def make_video(audio_path: str, cover_path: str, title: str, job_id: str) -> str:
    """
    静止画 + 音声波形のYouTube向け動画(MP4)を生成する。
    画面下部に showwaves のオーバーレイを置くシンプル構成。
    """
    _ensure_dir()

    if not cover_path or not os.path.exists(cover_path):
        cover_path = _generate_placeholder_cover(title, os.path.join(VIDEO_DIR, f"{job_id}_cover.png"))

    output = os.path.join(VIDEO_DIR, f"{job_id}.mp4")

    # 静止画をループ + 音声波形(showwaves)を半透明オーバーレイ
    filter_complex = (
        "[0:v]scale=1280:720,setsar=1[bg];"
        "[1:a]showwaves=s=1280x140:mode=cline:colors=white|cyan:rate=25[wave];"
        "[bg][wave]overlay=0:H-h-40:format=auto[v]"
    )

    cmd = (
        f"{shlex.quote(FFMPEG_BIN)} -y -loop 1 -i {shlex.quote(cover_path)} -i {shlex.quote(audio_path)} "
        f'-filter_complex "{filter_complex}" '
        "-map [v] -map 1:a "
        "-c:v libx264 -tune stillimage -pix_fmt yuv420p -r 25 "
        "-c:a aac -b:a 192k -shortest "
        f"{shlex.quote(output)}"
    )

    code, log = await _run(cmd)
    if code != 0 or not os.path.exists(output):
        raise RuntimeError(f"ffmpeg failed (code={code}): {log[-800:]}")
    return output
