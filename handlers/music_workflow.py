"""
LINE主導の音楽生成ワークフロー（Suno手動 + Bot自動投稿ハイブリッド）。

ユーザー操作:
  1. 「曲：<テーマ>」 → Botが歌詞・タイトル・概要欄を生成
  2. ユーザーがSunoで手動生成 → Public公開 → 共有URLをLINEに送信
  3. ユーザーがGensparkでサムネ生成 → LINEに画像送信
  4. 「OK2」 → Botが動画化（静止画+音声波形）
  5. 「OK3 タイトル:.. 説明:..」 → BotがYouTubeへ自動投稿

その他コマンド:
  状態                    現在のジョブを表示
  やり直し1 <指示>        歌詞を再生成
"""
import os
import re
import asyncio

from handlers import job_store
from handlers import lyrics_handler
from handlers import suno_handler
from handlers import video_handler
from handlers import youtube_handler

YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "public")
AUDIO_DIR = os.getenv("AUDIO_DIR", "/tmp/nori_audio")
THUMB_DIR = os.getenv("THUMB_DIR", "/tmp/nori_thumbs")


def is_music_command(text: str) -> bool:
    """通常のClaude応答ではなく音楽ワークフローに渡すべきメッセージか判定"""
    if not text:
        return False
    if re.match(r"^\s*(曲[:：]|OK\s*[23]|やり直し\s*1|状態\s*$)", text):
        return True
    if suno_handler.find_suno_url(text):
        return True
    return False


async def handle(user_id: str, text: str) -> str:
    job_store.init_db()
    text = text.strip()

    if text == "状態":
        job = job_store.get_latest_job(user_id)
        return _status_text(job) if job else "🎵 進行中のジョブはないよ。「曲：<テーマ>」で始めてね"

    m = re.match(r"^曲[:：]\s*(.+)$", text)
    if m:
        return await _step_lyrics(user_id, m.group(1).strip())

    job = job_store.get_latest_job(user_id)
    if not job:
        return "🎵 進行中のジョブがないよ。「曲：<テーマ>」で始めてね"

    if re.match(r"^やり直し\s*1", text):
        instruction = re.sub(r"^やり直し\s*1\s*", "", text)
        new_theme = (job["theme"] or "") + (f" / 修正指示: {instruction}" if instruction else "")
        return await _step_lyrics(user_id, new_theme, existing_job_id=job["id"])

    suno_url = suno_handler.find_suno_url(text)
    if suno_url:
        return await handle_suno_url(user_id, suno_url, job)

    if re.match(r"^OK\s*2$", text):
        return await _step_video(job["id"])

    if re.match(r"^OK\s*3", text):
        title_match = re.search(r"タイトル[:：]\s*(.+?)(?=\s+説明[:：]|$)", text)
        desc_match = re.search(r"説明[:：]\s*(.+)$", text)
        custom_title = title_match.group(1).strip() if title_match else None
        custom_desc = desc_match.group(1).strip() if desc_match else None
        return await _step_youtube(job["id"], custom_title, custom_desc)

    return _help_text()


async def handle_suno_url(user_id: str, suno_url: str, job: dict = None) -> str:
    """SunoのURLを受け取り、MP3を非同期でDLしてジョブに紐付ける"""
    job_store.init_db()
    if job is None:
        job = job_store.get_latest_job(user_id)
    if not job:
        return "🎵 先に「曲：<テーマ>」でジョブを始めてね"
    job_store.update_job(job["id"], suno_url=suno_url)
    asyncio.create_task(_resolve_and_download_suno(job["id"], suno_url))
    return f"🎵 SunoのURLを受け取ったよ (job {job['id']})。MP3取得中..."


async def handle_image(user_id: str, image_path: str) -> str:
    """LINEの画像メッセージをサムネとしてジョブに紐付ける"""
    job_store.init_db()
    job = job_store.get_latest_job(user_id)
    if not job:
        return "🖼 先に「曲：<テーマ>」でジョブを始めてね"
    job_store.update_job(job["id"], thumbnail_path=image_path)
    job = job_store.get_job(job["id"])
    return _assets_status(job)


def _help_text() -> str:
    return (
        "🎵 受け付けたコマンドが分からないよ。\n"
        "・曲：<テーマ>\n"
        "・やり直し1 <指示>\n"
        "・SunoのURLをそのまま貼る\n"
        "・サムネ画像を送る\n"
        "・OK2（動画化）/ OK3 タイトル:〇〇 説明:〇〇（投稿）\n"
        "・状態"
    )


def _status_text(job: dict) -> str:
    return (
        f"🎵 ジョブ {job['id']} | ステージ: {job['stage']}\n"
        f"テーマ: {job.get('theme') or '-'}\n"
        f"タイトル: {job.get('title') or '-'}\n"
        f"Suno URL: {job.get('suno_url') or '-'}\n"
        f"音源DL: {'✅' if job.get('audio_path') else '-'}\n"
        f"サムネ: {'✅' if job.get('thumbnail_path') else '-'}\n"
        f"動画: {'✅' if job.get('video_path') else '-'}\n"
        f"YouTube: {job.get('youtube_url') or '-'}"
    )


def _assets_status(job: dict) -> str:
    has_audio = bool(job.get("audio_path"))
    has_thumb = bool(job.get("thumbnail_path"))
    if has_audio and has_thumb:
        return (
            f"✅ 音源・サムネ両方そろったよ (job {job['id']})\n"
            f"動画化するなら「OK2」、サムネ差し替えなら別画像を送ってね"
        )
    missing = []
    if not has_audio:
        missing.append("Sunoの公開URL")
    if not has_thumb:
        missing.append("サムネ画像")
    return f"📥 受け取ったよ。あと必要なもの: {' / '.join(missing)}"


async def _step_lyrics(user_id: str, theme: str, existing_job_id: str = None) -> str:
    if existing_job_id:
        job = job_store.update_job(existing_job_id, theme=theme, stage="lyrics")
    else:
        job = job_store.create_job(user_id, theme)
    data = await lyrics_handler.generate_lyrics(theme)
    job_store.update_job(
        job["id"],
        lyrics=data["lyrics"],
        style=data["style"],
        title=data["title"],
        description=data["description"],
        stage="assets",
    )
    return (
        f"📝 歌詞できたよ (job {job['id']})\n\n"
        f"【タイトル】{data['title']}\n"
        f"【スタイル】{data['style']}\n\n"
        f"{data['lyrics']}\n\n"
        f"---\n"
        f"次の手順:\n"
        f"1. Sunoでこの歌詞・スタイルで生成\n"
        f"2. 曲ページを「Public」公開してURLをコピー\n"
        f"3. URLをLINEに送る\n"
        f"4. Gensparkでサムネ画像を作ってLINEに送る\n"
        f"\n修正したい場合は「やり直し1 <指示>」"
    )


async def _resolve_and_download_suno(job_id: str, suno_url: str):
    from handlers import line_notifier
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        audio_url = await suno_handler.resolve_audio_url(suno_url)
        audio_path = os.path.join(AUDIO_DIR, f"{job_id}.mp3")
        await suno_handler.download(audio_url, audio_path)
        job_store.update_job(job_id, audio_url=audio_url, audio_path=audio_path)
        job = job_store.get_job(job_id)
        await line_notifier.push(job["user_id"], _assets_status(job))
    except Exception as e:
        job = job_store.get_job(job_id)
        if job:
            await line_notifier.push(
                job["user_id"],
                f"❌ MP3取得失敗: {str(e)[:300]}\nSunoの曲が「Public」公開になってるか確認してね",
            )


async def _step_video(job_id: str) -> str:
    job = job_store.get_job(job_id)
    if not job:
        return "❌ ジョブが見つからない"
    if not job.get("audio_path"):
        return "❌ 音源がまだないよ。SunoのURLを送ってね"
    if not job.get("thumbnail_path"):
        return "❌ サムネ画像がまだないよ。画像を送ってね"
    job_store.update_job(job_id, stage="video")
    asyncio.create_task(_render_video_and_notify(job_id))
    return f"🎬 動画化を始めたよ (job {job_id})。完了したら通知するね"


async def _render_video_and_notify(job_id: str):
    from handlers import line_notifier
    try:
        job = job_store.get_job(job_id)
        video_path = await video_handler.make_video(
            audio_path=job["audio_path"],
            cover_path=job["thumbnail_path"],
            title=job.get("title") or "untitled",
            job_id=job_id,
        )
        job_store.update_job(job_id, video_path=video_path, stage="video_ready")
        text = (
            f"🎬 動画できたよ (job {job_id})\n"
            f"ローカル: {video_path}\n\n"
            f"YouTube投稿するなら「OK3 タイトル:〇〇 説明:〇〇」（省略可）"
        )
        await line_notifier.push(job["user_id"], text)
    except Exception as e:
        job = job_store.get_job(job_id)
        if job:
            await line_notifier.push(job["user_id"], f"❌ 動画生成失敗: {str(e)[:300]}")


async def _step_youtube(job_id: str, custom_title: str = None, custom_desc: str = None) -> str:
    job = job_store.get_job(job_id)
    if not job or not job.get("video_path"):
        return "❌ 動画がまだない。先に「OK2」で動画化してね"
    job_store.update_job(job_id, stage="youtube")
    asyncio.create_task(_upload_and_notify(job_id, custom_title, custom_desc))
    return f"📤 YouTubeに送ってるよ (job {job_id})。完了したら通知するね"


async def _upload_and_notify(job_id: str, custom_title: str = None, custom_desc: str = None):
    from handlers import line_notifier
    try:
        job = job_store.get_job(job_id)
        result = await youtube_handler.upload_video(
            video_path=job["video_path"],
            title=custom_title or job.get("title") or "untitled",
            description=custom_desc or job.get("description") or "",
            tags=["Suno", "AI音楽"],
            privacy=YOUTUBE_PRIVACY,
        )
        job_store.update_job(job_id, youtube_url=result["url"], stage="done")
        text = (
            f"✅ YouTube投稿完了！(job {job_id})\n"
            f"視聴URL: {result['url']}\n"
            f"Studio: {result['studio_url']}\n"
            f"公開設定: {YOUTUBE_PRIVACY}"
        )
        await line_notifier.push(job["user_id"], text)
    except Exception as e:
        job = job_store.get_job(job_id)
        if job:
            await line_notifier.push(job["user_id"], f"❌ YouTube投稿失敗: {str(e)[:300]}")
