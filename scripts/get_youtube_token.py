"""
YouTube Data API v3 にアップロードするための refresh_token を取得するワンタイムスクリプト。

【事前準備：Google Cloud Console での作業】

1. https://console.cloud.google.com/ にアクセスして、新規プロジェクトを作成
   （例: nori-youtube-bot）
2. 左メニュー → APIとサービス → ライブラリ → 「YouTube Data API v3」を検索
   → 有効化
3. 左メニュー → APIとサービス → OAuth同意画面
   - User Type: 外部
   - アプリ名: nori-ai-assistant（任意）
   - サポートメール: 自分のメール
   - スコープ: そのまま次へ
   - テストユーザー: 投稿に使うYouTubeチャンネルに紐づく
     Googleアカウントを追加（必須！）
4. 左メニュー → APIとサービス → 認証情報 → 認証情報を作成
   → OAuthクライアントID
   - アプリの種類: デスクトップアプリ
   - 名前: nori-cli（任意）
   → JSON をダウンロード（以後 client_secret.json として保存）

【このスクリプトの使い方（ローカルPCで実行）】

  pip install google-auth-oauthlib
  python scripts/get_youtube_token.py path/to/client_secret.json

ブラウザが開いて Googleアカウントでログイン → 許可 を押すと
ターミナルに refresh_token が表示されます。

その値を Render の環境変数に設定してください:
  YOUTUBE_CLIENT_ID       = client_secret.json の "client_id"
  YOUTUBE_CLIENT_SECRET   = client_secret.json の "client_secret"
  YOUTUBE_REFRESH_TOKEN   = ↓のスクリプトが出力した値

※ refresh_token は1度だけ発行されます。失くしたら同じ手順で再取得可能。
※ Sunoで作った曲を投稿する用途のチャンネルに紐づくGoogleアカウントで
   ログインしてください。
"""
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_youtube_token.py <client_secret.json>")
        sys.exit(1)

    secret_path = Path(sys.argv[1])
    if not secret_path.exists():
        print(f"❌ {secret_path} が見つからない")
        sys.exit(1)

    with secret_path.open() as f:
        secret = json.load(f)
    info = secret.get("installed") or secret.get("web") or {}
    client_id = info.get("client_id", "")
    client_secret = info.get("client_secret", "")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    # ローカルサーバーモードでブラウザ認可。port=0で空きポート自動取得
    creds = flow.run_local_server(
        port=0,
        prompt="consent",       # 必ず再同意 → refresh_token を確実に発行
        access_type="offline",  # refresh_token を取得するために必須
        open_browser=True,
    )

    print("\n" + "=" * 60)
    print("✅ 認証完了！以下を Render の環境変数に設定してください:")
    print("=" * 60)
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)
    print("\n⚠️ refresh_token は機密情報。Renderのenvに直接貼って、")
    print("   コードや公開リポジトリにはコミットしないこと。")


if __name__ == "__main__":
    main()
