# Muse Realtime Bridge

M5Stack StopWatchの音声を、Muse VM上のPythonプログラムからOpenAI Realtime APIへ中継します。OpenAI公式Python SDKを使い、APIキー・モデル・声・指示文をVM側で管理します。

```text
StopWatch（ファームウェアの変更が必要）
    ↕ WebSocket / PCM16LE 24 kHz / BRIDGE_TOKEN
Muse VM: muse-realtime-bridge
    ↕ OpenAI Python SDK / OPENAI_API_KEY
OpenAI Realtime API
```

初版は独立したWebSocketサーバーです。**Muse標準の `/voice/realtime` やHTTP-over-Noiseに追加する実装ではありません。** VMのポートへの外部接続経路は別途必要です。Museへの作業依頼は未実装です。

## 必要なもの

- Python 3.12以上（セットアップスクリプトは3.12を選択）と [uv](https://docs.astral.sh/uv/getting-started/installation/)
- OpenAI APIキーと、設定したRealtimeモデルを利用できるAPIアカウント
- VMから `api.openai.com:443` へのWebSocket接続
- 端末からVM内の中継へ到達できる経路（ローカル試験は不要）

## セットアップ

```bash
git clone https://github.com/shuntaka9576/muse-realtime-bridge.git
cd muse-realtime-bridge
./scripts/setup.sh
```

`.env` にOpenAI APIキーを設定し、次のコマンドで生成した値を `BRIDGE_TOKEN` に設定します。既存の `.env` はスクリプトで上書きしません。

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
chmod 600 .env
```

| 設定 | 用途 | 既定値 |
| --- | --- | --- |
| `OPENAI_API_KEY` | VMからOpenAIへの認証。端末へ渡さない | 必須 |
| `BRIDGE_TOKEN` | 端末から自作中継への認証。32文字以上のランダム値 | 必須 |
| `BRIDGE_HOST` / `BRIDGE_PORT` | 中継の待ち受け | `127.0.0.1` / `8787` |
| `OPENAI_REALTIME_MODEL` | 利用するRealtimeモデル | `gpt-realtime` |
| `OPENAI_REALTIME_VOICE` | 音声 | `marin` |
| `OPENAI_REALTIME_INSTRUCTIONS` | 会話の指示文 | 日本語で短く自然に応答 |
| `BRIDGE_MAX_CONNECTIONS` | 同時会話数の上限 | `1` |
| `BRIDGE_SESSION_SECONDS` | 1接続の最大時間 | `600` |
| `BRIDGE_IDLE_SECONDS` | 端末からイベントが来ない場合の切断時間 | `60` |

`BRIDGE_TOKEN` はMuseのSDKトークンや `vm_auth_token` とは別物です。本プログラムはMuseの認証情報を取得・検証しません。端末に保持する秘密情報がなくなるわけではありません。

## 起動・停止

```bash
.venv/bin/muse-realtime-bridge --env-file .env
```

Ctrl+Cで停止します。起動時は設定検証と待ち受けのみで、端末が認証済み接続を開始するまでOpenAI APIには接続しません。ログは接続ID・開始終了・エラー種別のみで、音声、会話本文、キーは記録しません。

別ターミナルでプロセスの生存を確認できます。

```bash
curl --fail http://127.0.0.1:8787/healthz
```

`/healthz` はOpenAIへの接続成功を示すものではありません。

## OpenAIとの疎通確認

以下は実際のOpenAI APIへ接続します。API利用に応じた料金が発生します。

```bash
.venv/bin/muse-realtime-smoke --env-file .env
```

`bridge.ready` と表示されたら、認証・Realtime接続・セッション設定まで成功です。入力音声を送る場合は、24 kHz・モノラル・16-bit PCMのWAVを用意します。

```bash
ffmpeg -i recording.m4a -ar 24000 -ac 1 -c:a pcm_s16le input.wav
.venv/bin/muse-realtime-smoke --env-file .env --input input.wav --output reply.wav
```

入力は100 ms〜60秒です。返答を `reply.wav` に保存します。既存の出力ファイルは上書きしません。これはファイルでの音声往復試験で、マイクのライブ入力・スピーカー再生・割り込みは端末側で確認します。

## VMで常駐させる

systemdユーザーサービスを利用でき、`~/muse-realtime-bridge` に配置した場合の例です。別の配置先ではunitの2つのパスを変更してください。

```bash
mkdir -p ~/.config/systemd/user
cp deploy/muse-realtime-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now muse-realtime-bridge
systemctl --user status muse-realtime-bridge
journalctl --user -u muse-realtime-bridge -n 50
```

停止は `systemctl --user disable --now muse-realtime-bridge`。Muse VMでユーザーサービスが使えるか、ログアウト後に継続するか、VM再配置後にファイルが残るかは実環境で確認してください。サービスが使えない場合も、上のフォアグラウンド起動で試験できます。

## 端末から接続する

初期状態はループバック待ち受けです。VMの公開ポート、WebSocket対応のTLSリバースプロキシ、またはトンネルなど、利用できる経路を確認してから接続してください。外部からは `wss://` を使い、Authorizationヘッダーを中継まで保持します。本リポジトリは外部公開やVMの標準デーモン変更を自動では行いません。

端末側は [通信仕様](docs/protocol.md) に沿って、接続先と `BRIDGE_TOKEN`、24 kHz PCMの送受信、Push-to-talk、割り込み時の再生位置報告を実装します。[muse-gadget-sdk](https://github.com/shuntaka9576/muse-gadget-sdk) の既存ファームウェアをそのまま使うことはできません。

## Museに渡す依頼文

[Muse向けセットアップ手順](docs/muse-setup.md) を参照してください。以下をチャットへ渡す想定です。

```text
https://github.com/shuntaka9576/muse-realtime-bridge
このリポジトリのREADME.mdとdocs/muse-setup.mdを読み、VM内にセットアップしてください。
既存のMuseデーモンは変更せず、まず127.0.0.1で起動してhealthzを確認してください。
APIキーやトークンの値はログや返信に含めず、設定の有無と疎通結果を報告してください。
端末から接続する経路は別途確認し、利用可能な方法を報告してください。
```

## 開発・検証状況

```bash
uv sync --frozen --python 3.12
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

テストはローカルの模擬OpenAI WebSocketサーバーと本物のOpenAI Python SDKを使います。外部APIへの通信・課金はありません。認証、セッション設定、音声往復、キャンセルと履歴切り詰め、切断、接続上限、タイムアウトを検証します。

実際のOpenAI API・Muse VM・StopWatchを組み合わせた動作は未検証です。
