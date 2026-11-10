# Muse向けセットアップ手順

## OpenAI APIキーの登録方針

OpenAI APIキーはMuseの認証情報ストアへ登録する。チャットへの貼り付けや、中継の `.env` への実キー保存を求めない。

[Meta公式の説明](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse)では、実キーをエージェントの実行環境から分離し、プログラムには代替トークン（surrogate token）を渡す。Sentinelが外部通信を許可した後、ネットワーク境界で実キーを挿入する。

この中継のPython SDK／WebSocket接続で利用できるかは未検証。以下を確認する。

- ユーザーへ専用の認証情報入力画面を提示できるか
- `api.openai.com` のRealtime接続用に代替トークンを取得・使用する方法
- WebSocket Upgrade時の `Authorization: Bearer ...` をSentinelが置換できるか
- SDKに必要なプロキシ・証明書・宛先許可の設定と、常駐プロセスでも利用できるか

現在のコードは `OPENAI_API_KEY` 環境変数を読み取るだけで、認証情報ストアの呼び出しや代替トークンの更新処理を実装していない。VM内の正式な手順を確認し、必要な接続処理を調整する。代替トークンを単に環境変数へ入れれば動くとは仮定しない。

利用できない場合は実キー保存や通信制御の迂回へ切り替えず、理由と未確認事項を報告する。

## VM内での導入

1. `python3 --version`、`git --version`、`uv --version` で実行環境を確認する。Python 3.12以上を使う。uvがなければREADMEの公式インストール案内を参照する。
2. `~/muse-realtime-bridge` にクローンし、`./scripts/setup.sh` を実行する。既存のチェックアウトや `.env` を上書きしない。
3. 上記の認証情報ストアの手順でキーを登録し、代替トークンと接続処理を設定する。実キーを読み出したり、返信やログへ出したりしない。登録やWebSocket対応が確認できなければ、その段階で結果を報告する。
4. 専用の `BRIDGE_TOKEN` を新規生成し、`.env` に保存する。Museの `vm_auth_token` やデバイストークンを流用しない。`.env` の権限は600にする。
5. `.venv/bin/muse-realtime-bridge --env-file .env` で起動する。SDKへ渡す認証値が未設定では起動しない。
6. 別のプロセスから `curl --fail http://127.0.0.1:8787/healthz` を実行する。
7. 実API試験を行う段階で `.venv/bin/muse-realtime-smoke --env-file .env` を実行し、`bridge.ready` を確認する。音声往復はREADMEのWAV試験で確認する。
8. 常駐が必要ならsystemdユーザーサービスの利用可否を確認し、READMEのunitを使う。フォアグラウンド試験のプロセスを停止してからサービスを起動し、二重起動を避ける。

## 端末への接続経路

このリポジトリは、Muse標準のHTTP-over-Noiseで任意の自作プロセスへ到達できると仮定していない。`/fetch_vms` で取得した接続先に、この中継の `/realtime` が自動的に追加されるわけではない。

VM内から使えるポート公開・TLSプロキシ・トンネルを調べ、WebSocket UpgradeとAuthorizationヘッダーを保持できる方法を報告する。既存のMuseデーモンや `/voice/realtime` のルートを変更しない。

端末に必要なのは中継の `wss://.../realtime` URLと `BRIDGE_TOKEN`。OpenAIの実キーは認証情報ストアに残し、端末へ渡さない。端末へのトークン設定方法はユーザーと調整する。

## 報告する内容

- 使用したコミット、Pythonバージョン、セットアップ結果
- 認証情報ストアへの登録状況、代替トークンとWebSocketでの実キー挿入の確認結果（値は含めない）
- 中継専用トークンの設定済み／未設定（値は含めない）
- healthz、OpenAIセッション初期化、音声往復それぞれの確認結果
- 起動方法と停止方法
- 端末からの接続経路の確認結果、未解決事項

healthzの成功を、音声会話や実機の成功として報告しない。
