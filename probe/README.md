# PCからの接続確認クライアント

`client.py`はVMトークンを取得し、SDKのNoise接続経由でnonceの往復を確認します。
サーバーは音声中継と共通の `muse-realtime-bridge` です。
旧 `server.py` は統合・削除しました。[README](../README.md)の手順を使ってください。

既存のaccess/device token、またはSDKの`pairing.json`が必要です。
トークン取得だけなら`--fetch-only`、複数VMから選ぶ場合は`--vm-id`、
転送先パスを変える場合は`--path`を指定します。
標準と異なるNoiseホストを使う場合だけ、確認した宛先を`--noise-host`で明示します。

トークン更新は行いません。期限切れの場合は既存SDKで認証情報を更新してください。
アカウントAPIは`https://api.muse.ai`限定で、HTTP・WebSocketのリダイレクトを追いません。
TLS検証を有効にし、非表示入力が使えなければ中止します。端末登録は行いません。

検証リクエストは `GET /probe/echo?nonce=<ランダムな32桁の16進数>` です。
サーバー単体の応答とMuse認証経由の疎通は別の確認です。
404だけでは、指定パスにルートがないことしか分かりません。
