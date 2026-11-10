# Muse VMへの接続検証

PCからMuseの認証を通り、VM内の自作サーバーへ接続できるかを確認します。
**今回使うのは `probe/server.py` と `probe/client.py` だけです。**
OpenAIの設定・APIキー・`BRIDGE_TOKEN` は不要です。

```text
PC → fetch_vmsでvm_auth_tokenを取得 → Museの認証済みNoise接続 → VM内のechoサーバー
```

## Museに渡す設定用プロンプト

```text
https://github.com/shuntaka9576/muse-realtime-bridge
VM側の以前の検証環境は削除したので、最新mainを新しくクローンし、
READMEに従ってechoサーバーだけをセットアップしてください。

probe/server.pyを127.0.0.1:8788で起動し、VM内のcurlで応答を確認してください。
次に、Museの認証済みHTTP-over-Noise接続のPOST /probe/echoを、
http://127.0.0.1:8788/probe/echoへ転送できるか確認してください。
利用可能な設定機構があれば、このパスだけの転送設定を追加してください。
なければそこで止め、制約を報告してください。

既存のMuseデーモン・認証・既存ルートは変更しないでください。
外部ポート公開や公開トンネルは作らず、キーやトークンの値も表示しないでください。
OpenAIの設定、scripts/setup.shの実行、音声中継の起動は不要です。

ローカルechoの結果、転送可否と設定箇所、PCから指定するパス、
起動・停止方法を報告してください。PC側のクライアントはこちらで実行します。
```

## VM側：サーバーを起動する

Python 3とGitだけを使います。追加パッケージは不要です。

```sh
git clone https://github.com/shuntaka9576/muse-realtime-bridge.git
cd muse-realtime-bridge
python3 probe/server.py
```

別ターミナルで応答を確認します。サーバーはCtrl+Cで停止できます。

```sh
curl --fail http://127.0.0.1:8788/probe/echo \
  -H 'Content-Type: application/json' \
  -d '{"nonce":"0123456789abcdef0123456789abcdef"}'
```

同じ`nonce`が返ればサーバー単体は動いています。
**Noise接続からこのサーバーへの転送設定は別途必要で、実現できるかは未確認です。**

## PC側：認証して接続する

VM側の転送設定ができたら、PCでこのリポジトリを開きます。
[uv](https://docs.astral.sh/uv/)と、隣のディレクトリにある
[Muse Gadget SDK](https://github.com/shuntaka9576/muse-gadget-sdk)を使います。

```sh
uv run --no-project --python 3.12 \
  --with ../muse-gadget-sdk/linux --with 'websockets>=15,<16' \
  python probe/client.py
```

非表示の入力欄へ既存のMuseのaccess/device tokenを入力します。
ペアリング済みSDKのファイルがあれば、代わりに
`--pairing-file /path/to/pairing.json`を追加できます。初回のログインやペアリングは別途必要です。

クライアントはVMトークン取得・Noise接続・echo往復の結果を順に表示します。
ランダムな`nonce`が一致すると`PASS`になります。トークンの値は表示・保存しません。
VMトークン取得だけを試す場合は`--fetch-only`を追加してください。

ローカルechoと自動テストは確認済みです。実VMを経由したPCからの疎通は未確認です。
