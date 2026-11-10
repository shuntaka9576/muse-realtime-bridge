# Muse向けセットアップ手順

## VM内での導入

1. `python3 --version`、`git --version`、`uv --version` で実行環境を確認する。Python 3.12以上を使う。uvがなければREADMEの公式インストール案内を参照する。
2. `~/muse-realtime-bridge` にクローンし、`./scripts/setup.sh` を実行する。既存のチェックアウトや `.env` を上書きしない。
3. `.env` の `OPENAI_API_KEY` をユーザーの指定した方法で設定する。値を返信やログへ出さない。未提供なら設定が必要であることだけを報告する。
4. 専用の `BRIDGE_TOKEN` を新規生成し、`.env` に保存する。Museの `vm_auth_token` やデバイストークンを流用しない。`.env` の権限は600にする。
5. `.venv/bin/muse-realtime-bridge --env-file .env` で起動する。APIキー未設定では起動しない。
6. 別のプロセスから `curl --fail http://127.0.0.1:8787/healthz` を実行する。
7. 実API試験を行う段階で `.venv/bin/muse-realtime-smoke --env-file .env` を実行し、`bridge.ready` を確認する。音声往復はREADMEのWAV試験で確認する。
8. 常駐が必要ならsystemdユーザーサービスの利用可否を確認し、READMEのunitを使う。フォアグラウンド試験のプロセスを停止してからサービスを起動し、二重起動を避ける。

## 端末への接続経路

このリポジトリは、Muse標準のHTTP-over-Noiseで任意の自作プロセスへ到達できると仮定していない。`/fetch_vms` で取得した接続先に、この中継の `/realtime` が自動的に追加されるわけではない。

VM内から使えるポート公開・TLSプロキシ・トンネルを調べ、WebSocket UpgradeとAuthorizationヘッダーを保持できる方法を報告する。既存のMuseデーモンや `/voice/realtime` のルートを変更しない。

端末に必要なのは中継の `wss://.../realtime` URLと `BRIDGE_TOKEN`。`OPENAI_API_KEY` はVM内に残す。端末へのトークン設定方法はユーザーと調整する。

## 報告する内容

- 使用したコミット、Pythonバージョン、セットアップ結果
- APIキーと中継トークンの設定済み／未設定（値は含めない）
- healthz、OpenAIセッション初期化、音声往復それぞれの確認結果
- 起動方法と停止方法
- 端末からの接続経路の確認結果、未解決事項

healthzの成功を、音声会話や実機の成功として報告しない。
