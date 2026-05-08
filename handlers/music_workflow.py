"""
LINE主導の音楽生成ワークフロー。各ステップでユーザー承認を求める。

コマンド (LINE上):
  曲：<テーマ>           新規ジョブ開始（歌詞生成へ）
  OK1                   歌詞OK → SUNO生成へ
  やり直し1 <指示>       歌詞を再生成（指示は任意）
  OK2                   音源OK → 動画化へ
  やり直し2             SUNO再生成
  OK3 タイトル:.. 説明:.. 動画OK → YouTubeへアップ（タイトル/説明上書き任意）
  状態                   現在のジョブ確認
"""
import os
import re
import asyncio

from handlers import job_store
from handlers import lyrics_handler
from handlers import suno_handler
from handlers import video_handler
from handlers import youtube_handler

YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "public")  # private/unlisted/public
AUDIO_DIR = os.getenv("AUDIO_DIR", "/tmp/nori_audio")


def is_music_command(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.match(r"^\s*(曲[:：]|OK\s*[123]|やり直し\s*[123]|状態\s*$)", text)
    )


async def handle(user_id: str, text: str) -> str:
    """LINEからの音楽コマンドを処理し、ユーザーに返す文字列を返す"""
    job_store.init_db()
    text = text.strip()

    # 状態確認
    if text == "状態":
        job = job_store.get_latest_job(user_id)
        if not job:
            return "🎵 進行中のジョブはないよ。「曲：<テーマ>」で始めてね"
        return _status_text(job)

    # 新規ジョブ
    m = re.match(r"^曲[:：]\s*(.+)$", text)
    if m:
        theme = m.group(1).strip()
        return await _step_lyrics(user_id, theme)

    # 進捗確認用にジョブを引く
    job = job_store.get_latest_job(user_id)
    if not job:
        return "🎵 進行中のジョブがないよ。「曲：<テーマ>」で始めてね"

    # 各ステップの承認
    if re.match(r"^OK\s*1$", text):
        return await _step_suno(job["id"])
    if re.match(r"^やり直し\s*1", text):
        instruction = re.sub(r"^やり直し\s*1\s*", "", text)
        new_theme = (job["theme"] or "") + (f" / 修正指示: {instruction}" if instruction else "")
        return await _step_lyrics(user_id, new_theme, existing_job_id=job["id"])
    if re.match(r"^OK\s*2$", text):
        return await _step_video(job["id"])
    if re.match(r"^やり直し\s*2", text):
        return await _step_suno(job["id"], regenerate=True)
    if re.match(r"^OK\s*3", text):
        title_match = re.search(r"タイトル[:：]\s*(.+?)(?=\s+説明[:：]|$)", text)
        desc_match = re.search(r"説明[:：]\s*(.+)$", text)
        custom_title = title_match.group(1).strip() if title_match else None
        custom_desc = desc_match.group(1).strip() if desc_match else None
        return await _step_youtube(job["id"], custom_title, custom_desc)

    return (
        "🎵 受け付けたコマンドが分からないよ。\n"
        "・曲：<テーマ>\n・OK1 / やり直し1\n・OK2 / やり直し2\n"
        "・OK3 タイトル:〇〇 説明:〇〇\n・状態"
    )


def _status_text(job: dict) -> str:
    return (
        f"🎵 ジョブ {job['id']} | ステージ: {job['stage']}\n"
        f"テーマ: {job.get('theme') or '-'}\n"
        f"タイトル: {job.get('title') or '-'}\n"
        f"音源: {job.get('audio_url') or '-'}\n"
        f"YouTube: {job.get('youtube_url') or '-'}"
    )


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
        stage="lyrics",
    )
    return (
        f"📝 歌詞できたよ (job {job['id']})\n\n"
        f"【タイトル】{data['title']}\n"
        f"【スタイル】{data['style']}\n\n"
        f"{data['lyrics']}\n\n"
        f"---\n"
        f"OKなら「OK1」、修正したいなら「やり直し1 <指示>」"
    )


async def _step_suno(job_id: str, regenerate: bool = False) -> str:
    job = job_store.get_job(job_id)
    if not job or not job.get("lyrics"):
        return "❌ 歌詞がない。「曲：〇〇」から始めてね"
    job_store.update_job(job_id, stage="music")

    task_id = await suno_handler.submit_generation(
        lyrics=job["lyrics"], style=job["style"] or "J-POP", title=job["title"] or "untitled"
    )
    job_store.update_job(job_id, suno_task_id=task_id)

    # ポーリングはバックグラウンドで実行
    asyncio.create_task(_poll_suno_and_notify(job_id, task_id))

    return (
        f"🎶 SUNOに投入したよ (task {task_id[:8]}...)。\n"
        f"完了したら通知するね（数分かかる）"
    )


async def _poll_suno_and_notify(job_id: str, task_id: str):
    """完了を待ち、ジョブを更新する。LINE通知はmain側のpush helperを呼ぶ。"""
    from handlers import line_notifier  # 後方依存を避けるため遅延import
    try:
        info = await suno_handler.wait_until_complete(task_id)
        job_store.update_job(
            job_id,
            audio_url=info["audio_url"],
            cover_url=info.get("image_url"),
        )
        job = job_store.get_job(job_id)
        text = (
            f"🎵 音源できたよ (job {job_id})\n"
            f"{info['audio_url']}\n\n"
            f"視聴して問題なければ「OK2」、再生成するなら「やり直し2」"
        )
        await line_notifier.push(job["user_id"], text)
    except Exception as e:
        from handlers import line_notifier
        job = job_store.get_job(job_id)
        if job:
            await line_notifier.push(job["user_id"], f"❌ SUNO生成失敗: {str(e)[:300]}")


async def _step_video(job_id: str) -> str:
    job = job_store.get_job(job_id)
    if not job or not job.get("audio_url"):
        return "❌ 音源がない。先にSUNO生成を完了させてね"
    job_store.update_job(job_id, stage="video")

    asyncio.create_task(_render_video_and_notify(job_id))
    return f"🎬 動画化を始めたよ (job {job_id})。完了したら通知するね"


async def _render_video_and_notify(job_id: str):
    from handlers import line_notifier
    try:
        job = job_store.get_job(job_id)
        os.makedirs(AUDIO_DIR, exist_ok=True)
        audio_path = os.path.join(AUDIO_DIR, f"{job_id}.mp3")
        await suno_handler.download(job["audio_url"], audio_path)

        cover_path = ""
        if job.get("cover_url"):
            cover_path = os.path.join(AUDIO_DIR, f"{job_id}_cover.jpg")
            await suno_handler.download(job["cover_url"], cover_path)

        video_path = await video_handler.make_video(
            audio_path=audio_path,
            cover_path=cover_path,
            title=job.get("title") or "untitled",
            job_id=job_id,
        )
        job_store.update_job(job_id, video_path=video_path)
        text = (
            f"🎬 動画できたよ (job {job_id})\n"
            f"ローカル: {video_path}\n\n"
            f"YouTube投稿するなら「OK3 タイトル:〇〇 説明:〇〇」（省略可）\n"
            f"再生成は「やり直し2」"
        )
        await line_notifier.push(job["user_id"], text)
    except Exception as e:
        job = job_store.get_job(job_id)
        if job:
            await line_notifier.push(job["user_id"], f"❌ 動画生成失敗: {str(e)[:300]}")


async def _step_youtube(job_id: str, custom_title: str = None, custom_desc: str = None) -> str:
    job = job_store.get_job(job_id)
    if not job or not job.get("video_path"):
        return "❌ 動画がない。先に「OK2」で動画化してね"
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
            tags=["SUNO", "AI音楽"],
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
