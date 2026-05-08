"""
YouTube Data API v3 にアップロードするための refresh_token を取得するワンタイムスクリプト。

【事前準備：Google Cloud Console での作業】

1. https://console.cloud.google.com/ にアクセスして、新規プロジェクトを作成
   （例: nori-youtube-bot）
2. 左メニュー → APIとサービス → ライブラリ → 「YouTube Data API v3」を検索
   → 有効化
3. 左メニュー → Google Auth Platform → 対象（オーディエンス）
   - User Type: 外部
   - 公開ステータス: テスト中（このままでOK）
   - テストユーザー: 投稿に使うYouTubeチャンネルに紐づく
     Googleアカウントを「+ Add users」で追加（必須！）
4. 左メニュー → Google Auth Platform → データアクセス
   - 「スコープを追加または削除」→ youtube.upload にチェック → 更新
5. 左メニュー → Google Auth Platform → クライアント → クライアントを作成
   - アプリの種類: デスクトップアプリ
   - 名前: nori-cli（任意）
   → JSON をダウンロード（以後 client_secret.json として保存）

【このスクリプトの使い方（ローカルPCで実行）】

  pip install google-auth-oauthlib
  python scripts/get_youtube_token.py path/to/client_secret.json

ブラウザが開いて Googleアカウント（手順3で追加したテストユーザー）でログイン
→ 「このアプリは確認されていません」と出たら「詳細」→「(アプリ名)に移動」
→ 許可 を押すと、ターミナルに refresh_token が表示されます。

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

    if not client_id or not client_secret:
        print("❌ client_secret.json の形式が不正（installed/web セクションが見つからない）")
        print("   Google Cloud Console の「クライアント」で『デスクトップアプリ』として作成したか確認")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    try:
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
            open_browser=True,
        )
    except Exception as e:
        print(f"❌ 認証フローでエラー: {e}")
        print("   ・テストユーザーに自分のGoogleアカウントを追加したか確認")
        print("   ・YouTube Data API v3 が有効化されているか確認")
        sys.exit(1)

    if not creds.refresh_token:
        print("❌ refresh_token が取得できなかった。Googleアカウント側でアプリのアクセス権を")
        print("   一度取り消してから再実行してください:")
        print("   https://myaccount.google.com/permissions")
        sys.exit(1)

    # バックアップとして .env.youtube に保存
    out_path = Path(".env.youtube")
    out_path.write_text(
        f"YOUTUBE_CLIENT_ID={client_id}\n"
        f"YOUTUBE_CLIENT_SECRET={client_secret}\n"
        f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n"
    )

    print("\n" + "=" * 60)
    print("✅ 認証完了！以下を Render の環境変数に設定してください:")
    print("=" * 60)
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)
    print(f"\n📝 上記内容は {out_path.resolve()} にも保存しました（.gitignore推奨）")
    print("\n⚠️ refresh_token は機密情報。Renderのenvに直接貼って、")
    print("   コードや公開リポジトリにはコミットしないこと。")


if __name__ == "__main__":
    main()
