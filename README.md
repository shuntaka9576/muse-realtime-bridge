# Muse Realtime Bridge

**1つのサーバーで、接続確認とOpenAI Realtime APIへの音声中継を行います。**
VMにセットアップするのはこのサーバーだけです。

| 同じサーバーの機能 | 接続先 |
| --- | --- |
| 起動確認 | `GET /healthz` |
| echo疎通確認 | `GET /probe/echo?nonce=<32桁の16進数>` |
| 音声中継 | WebSocket `/realtime` |

待ち受けはすべて`127.0.0.1:8787`です。ペアリング済みStopWatchでechoを確認した後、同じサーバーで音声を試します。
OpenAIの認証値が未設定でもechoは使えます。その場合、音声接続だけ503を返します。

## Museに渡す設定用プロンプト

```text
https://github.com/shuntaka9576/muse-realtime-bridge
README.mdを読み、echo確認とOpenAI音声中継のサーバーをVM内の127.0.0.1:8787にセットアップしてください。
OpenAI APIキーはMuseの認証情報ストアへ登録したいので、未登録なら専用の入力画面を提示してください。実キーをチャットや.envに保存せず、代替トークンとSentinelを利用してください。
VM内でechoとOpenAIへの音声接続を確認してください。
StopWatchからはNoise接続に成功していますが、GET /probe/echoがHTTP 403になります。拒否理由と、このサーバーへ転送する方法があるか調べてください。
既存のMuseデーモンや認証は変更せず、echo・OpenAI接続・転送可否を分けて報告してください。キーやトークンの値は表示しないでください。
```

## セットアップ条件

- OpenAI APIキーは専用入力画面からMuseの認証情報ストアへ登録し、代替トークンとSentinelを使います。既に登録済みなら再入力は不要です。実キーをチャット・ファイル・ログへ出さず、利用できなければそこで結果を報告してください。
- READMEのcurlでecho、OpenAI認証設定後にsmokeでWebSocket接続を確認してください。OpenAI未設定でもechoは使えます。
- 既存の認証済みNoise接続から、HTTP `/probe/echo`とWebSocket `/realtime`を転送できるか確認してください。既存のMuseデーモン・認証・ルートは改変せず、外部ポートや公開トンネルも作りません。転送機構がなければその制約を報告してください。

結果はecho・OpenAI接続・転送経路に分け、起動・停止方法を添えてください。
認証値は表示しません。StopWatchからのecho確認はユーザー側で実行します。

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

## StopWatch側：Museの認証経由で接続確認

検証の直前にVM内で`curl --fail http://127.0.0.1:8787/healthz`を実行し、停止していれば上記の手順で再起動します。自動復旧は前提にしません。

[Muse Gadget SDK](https://github.com/shuntaka9576/muse-gadget-sdk)のStopWatchビルドで
`CONFIG_MUSE_VM_PROBE=y`を有効にします。ペアリング済み端末をWi-Fiへ接続し、
画面が起きた状態で黄ボタンを押すとecho確認が始まります。このモードでは音声を送りません。

保存済みデバイストークンでVM情報を取得し、既存のLinkのNoise接続から
`GET /probe/echo?nonce=...`を送ります。SDKトークンや`vm_auth_token`を手入力せず、
追加の接続URLや独自トークンも端末に設定しません。

画面とログで`VM INFO`、`NOISE`、`ECHO`を順に確認します。`ECHO PASS`はサーバー名と
nonceが一致した場合だけ表示します。`HTTP 404`ならVM接続後のパスが応答しておらず、
bridgeへの転送成功ではありません。タイムアウトや接続失敗も区別します。

VM情報の確認は既存SDKの取得・更新処理を使い、echoはLinkが管理する接続に載せます。
端末から自作サーバーへ転送する機構は別途必要で、トークンを用意するだけでは届きません。

## 認証と現在の確認範囲

VM外からの認証はMuseの入口に任せ、サーバーはloopbackで待ち受けます。
このプロセス自体は`vm_auth_token`を検証しないため、同じVM内のプロセスからはアクセスできます。
loopback以外にbindする設定は起動時に拒否します。

Museからの報告では`systemctl --user`が利用できず、バックグラウンド起動したプロセスも翌朝には終了していました。終了原因は未特定で、再起動後の自動復旧手段も未確認です。現在は手動起動による検証用途で、常時稼働を前提にしていません。

**今回のVM調査では、任意のローカルポートへ転送する設定機構は見つかっていません。** echoのHTTP転送ができても、音声のWebSocket転送が
できるとは限りません。HTTP-over-Noiseとの変換が必要なら、その対応は別途必要です。
ローカルでは同一サーバーのechoと模擬OpenAIへの音声往復を自動テストしています。
実VM・実OpenAI・StopWatchを通した音声会話は未確認です。
