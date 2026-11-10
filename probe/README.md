# Muse VM認証・接続の最小検証

音声とOpenAIを外して、次の経路を確認します。

```text
クライアント --access/device token--> GET /fetch_vms
             <--VM情報 + vm_auth_token--
クライアント --vm_auth_token + Noise--> Muse VMのHTTPルーター
                                         ↓ 転送設定が可能かを確認
                                     127.0.0.1:8788 のechoサーバー
```

`vm_auth_token` はクライアント内で取得し、そのままSDKのVM認証に使います。
表示・保存しません。OpenAIキーと `BRIDGE_TOKEN` は不要です。
アカウント取得処理はSDKと同じAPI・ヘッダーを使い、認証情報が別の宛先へ
転送されないようリダイレクトを禁止しています。Noise処理はSDKを再利用します。

初回ログイン／BLEペアリングの実装は既存SDKに任せ、この検証では既存の
access/device tokenからVMトークンを取得します。期限切れの更新処理は追加していません。

## クライアント（手元のPC）

bridgeリポジトリで、隣のSDKのPython実装をインストールします。

```sh
uv sync --dev
uv pip install -e ../muse-gadget-sdk/linux
# まずVMトークンの取得だけ確認（非表示の入力欄にaccess/device tokenを入力）
uv run --no-sync python probe/client.py --fetch-only
# 続けてNoise接続とechoまで確認
uv run --no-sync python probe/client.py
```

ペアリング済みのSDK `pairing.json` がある場合は、どちらのコマンドにも
`--pairing-file /path/to/pairing.json` を付けられます（読み取りのみ）。
複数VMがあり既定VMを選べない場合は `--vm-id <id>` で指定します。
`--noise-host` と `--path` は実際の接続先・転送ルートに合わせて変更できます。
トークンをコマンド引数やチャットへ貼らないでください。

## サーバー（Muse VM）

追加のPython依存は不要です。

```sh
python3 probe/server.py
# VM内でサーバー単体を確認
curl --fail http://127.0.0.1:8788/probe/echo \
  -H 'Content-Type: application/json' \
  -d '{"nonce":"0123456789abcdef0123456789abcdef"}'
```

Museへ渡す全文は、[READMEの設定用プロンプト](../README.md#museに渡す設定用プロンプト)を使ってください。

**サーバーを起動するだけではNoise側にルートは生えません。** この転送設定が
可能かを調べるのが目的です。クライアントはHTTPステータスとランダムnonceの
一致で判定します。404だけなら「指定パスにルートがない」までしか分かりません。
`fetch_vms`、Noise接続、echo往復の成功を区別して表示します。
ローカルのecho成功は、実VMの転送成功を意味しません。
