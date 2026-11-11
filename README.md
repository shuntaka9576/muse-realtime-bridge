# Muse Realtime Bridge

**1つのサーバーで、接続確認とOpenAI Realtime APIへの音声中継を行います。**
VMにセットアップするのはこのサーバーだけです。

| 同じサーバーの機能 | 接続先 |
| --- | --- |
| 起動確認 | `GET /healthz` |
| echo疎通確認 | `GET /probe/echo?nonce=<32桁の16進数>` |
| 音声中継 | WebSocket `/realtime` |

待ち受けはすべて`127.0.0.1:8787`です。PCでechoを確認した後、同じサーバーで音声を試します。
OpenAIの認証値が未設定でもechoは使えます。その場合、音声接続だけ503を返します。

## Museに渡す設定用プロンプト

```text
https://github.com/shuntaka9576/muse-realtime-bridge
最新mainのREADMEに従い、echo確認と音声中継を兼ねるサーバーを
VM内の127.0.0.1:8787にセットアップしてください。サーバーは1つだけです。

OpenAI APIキーはMuseの認証情報ストアへ登録したいので、
専用の入力画面を提示してください。実キーをチャットや.envに保存しないでください。
Python SDKのWebSocket接続で代替トークンとSentinelの実キー挿入が使えるか確認し、
利用可能なら、その方法でサーバーに認証値を渡してください。
利用できなければ実キー保存へ切り替えず、確認結果を報告してください。

サーバーを起動し、READMEのcurlでechoを確認してください。
OpenAI認証が設定できた場合は、同じサーバーの音声接続も確認してください。
未設定ならechoを使える状態にし、音声は未設定と報告してください。

次に、Museの既存の認証済みVM接続からこのサーバーへ転送できるか調べてください。
echoはGET /probe/echo、音声はWebSocket /realtimeです。
それぞれの通信方式を転送できる機構があれば設定し、なければ制約を報告してください。
既存のMuseデーモン・認証・既存ルートを改変せず、外部ポートや公開トンネルは作らないでください。
今回のloopback構成ではBRIDGE_TOKENの生成は不要です。キーやトークンの値は表示しないでください。

echo、OpenAI音声接続、Muse経由の転送可否を区別し、起動・停止方法とともに報告してください。
PC側のクライアントはこちらで実行します。
```

## VM側：セットアップと起動

Python 3.12以上と[uv](https://docs.astral.sh/uv/)を使います。

```sh
git clone https://github.com/shuntaka9576/muse-realtime-bridge.git
cd muse-realtime-bridge
uv sync --frozen --no-dev --python 3.12
.venv/bin/muse-realtime-bridge
```

起動前に、Museで利用できる認証情報ストアの方法で`OPENAI_API_KEY`へ認証値を渡します。
代替トークンを利用できるかはMuse側での確認が必要です。実キーは`.env`へ保存しません。
設定を後から変えた場合は同じサーバーを再起動します。停止はCtrl+Cです。

別ターミナルから、同じサーバーの各機能を確認します。

```sh
curl --fail http://127.0.0.1:8787/healthz
curl --fail 'http://127.0.0.1:8787/probe/echo?nonce=0123456789abcdef0123456789abcdef'
# OpenAI設定済みの場合のみ。実際のOpenAI APIに接続します。
.venv/bin/muse-realtime-smoke
```

同じnonceが返ればecho成功、`bridge.ready`ならOpenAIの接続とセッション設定が成功です。
音声ファイルでの往復は、24 kHz・モノラル・16-bit PCMのWAVを指定します。

```sh
.venv/bin/muse-realtime-smoke --input input.wav --output reply.wav
```

## PC側：Museの認証経由で接続確認

VM側の転送設定ができたら、PCでこのリポジトリを開きます。
隣のディレクトリに[Muse Gadget SDK](https://github.com/shuntaka9576/muse-gadget-sdk)が必要です。

```sh
uv run --no-project --python 3.12 \
  --with ../muse-gadget-sdk/linux --with 'websockets>=15,<16' \
  python probe/client.py
```

非表示の入力欄へ既存のMuseのaccess/device tokenを入力します。
ペアリング済みSDKのファイルがあれば、代わりに`--pairing-file /path/to/pairing.json`を追加できます。
初回ログイン・ペアリングは別途必要です。クライアントはVMトークンを取得してNoise接続を開き、
echoのnonce一致を確認すると`PASS`を表示します。トークンの値は表示・保存しません。

## 認証と現在の確認範囲

VM外からの認証はMuseの入口に任せ、サーバーはloopbackで待ち受けます。
このプロセス自体は`vm_auth_token`を検証しないため、同じVM内のプロセスからはアクセスできます。
独自トークン未設定でloopback以外にbindする設定は起動時に拒否します。

**Muse経由の転送可否は未確認です。** echoのHTTP転送ができても、音声のWebSocket転送が
できるとは限りません。HTTP-over-Noiseとの変換が必要なら、その対応は別途必要です。
ローカルでは同一サーバーのechoと模擬OpenAIへの音声往復を自動テストしています。
実VM・実OpenAI・StopWatchを通した音声会話は未確認です。
