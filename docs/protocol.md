# 端末向け通信仕様 v1

接続先は `ws://127.0.0.1:8787/realtime`（VM内）、外部からはTLSで保護した `wss://<host>/realtime` です。1 WebSocket接続 = 1 OpenAI会話セッションです。Muse標準のHTTP-over-Noise／NDJSONとは異なり、**1 WebSocketテキストメッセージに1 JSONイベント**を送ります。

標準構成はloopback待ち受けで、VM外からの認証はMuseの入口に任せます。このプロセス自体は`vm_auth_token`を検証しません。Muse側の転送設定は未確認です。

独立した接続向けに`BRIDGE_TOKEN`を設定した場合だけ、HTTP Upgrade時に`Authorization: Bearer <BRIDGE_TOKEN>`が必要です。未設定でloopback以外へbindする設定は起動時に拒否します。ブラウザーのOrigin付き接続は受け付けません。

同じサーバー・ポートで`GET /probe/echo?nonce=<32桁の16進数>`と`GET /healthz`も提供します。OpenAI認証値が未設定でもこれらは利用でき、`/realtime`は503を返します。echoの成功は音声経路の成功を意味しません。

## 接続と音声形式

OpenAIへの接続と設定が完了すると、次のイベントが届きます。端末はこれを待ってから音声を送信します。

```json
{"type":"bridge.ready","protocol_version":1,"audio":{"encoding":"pcm_s16le","sample_rate":24000,"channels":1}}
```

上り・下りとも24 kHz、モノラル、PCM16LEをbase64でエンコードします。WAVヘッダーは送信しません。SDK既存の16 kHzマイク処理を使う場合は24 kHzへリサンプリングしてください。

1回のappendは最大200 ms（9,600 bytes）、推奨40 ms（1,920 bytes）。録音に合わせて送信してください。1発話は100 ms以上60秒以下です。短すぎる押下はcommitせずclearします。入力は2秒分までのバーストを許容し、持続レートは48,000 bytes/秒に制限します。

## 黄ボタンで話す

押下中、繰り返し送信します。

```json
{"type":"input_audio_buffer.append","audio":"<base64 PCM>"}
```

離したら、以下を順に送信します。

```json
{"type":"input_audio_buffer.commit"}
{"type":"response.create"}
```

`response.created`、`response.output_audio.delta`、`response.output_audio_transcript.delta`、`response.done` などのOpenAIイベントを受信します。`response.output_audio.delta.delta` をデコードして再生します。`response.done`は生成完了であり、スピーカーでの再生完了ではありません。`response.status` が `completed` かも確認してください。

下り音声は中継側で最大40 ms（1,920 bytes PCM）ずつに分割して送ります。

下りイベントには、音声に紐づく `item_id` と `content_index` が含まれます。音声生成が再生速度より速いため、端末側でも再生キューに上限を設けてください。受信が止まると中継側にもバックプレッシャーがかかり、送信タイムアウト時は接続を終了します。

## 返答中に黄ボタンを押す

1. 端末のスピーカーを直ちに止め、再生キューを捨てます。
2. 応答生成が続いている場合、`response.cancel` を送ります。
3. 再生済み時間を使って `conversation.item.truncate` を送り、聞いていない音声を履歴から除きます。
4. 新しいマイク音声をappendします。前の `response.done` を受けてから、次の `response.create` を送ります。ボタンを先に離した場合はcommit後、doneを待ってcreateします。

```json
{"type":"response.cancel"}
{"type":"conversation.item.truncate","item_id":"item_123","content_index":0,"audio_end_ms":1500}
```

`audio_end_ms`は受信した長さではなく、実際に再生した長さです。中継は送信済み音声の長さを超える値を拒否します。再生済み時間は端末側で計測します。割り込み済みの古い `response_id` の音声が通信中に残っていても再生しないでください。

初版は1応答の音声contentを `content_index=0` として扱います。最後の16音声itemをtruncation用に保持します。

## 青ボタン・異常終了

青ボタンではWebSocketをcloseします。中継がOpenAI接続を閉じます。再接続時は新しい会話になります。会話の自動復元や音声の再送は行いません。

接続後のエラーは `{"type":"bridge.error","code":"..."}` とcloseで通知します。認証エラーはHTTP 401、未知のパスは404、同時接続上限はWebSocket close 1013です。大きすぎる入力はclose 1009になります。

主なcodeは `audio_too_short`、`invalid_audio`、`response_still_pending`、`input_idle_timeout`、`session_timeout`、`upstream_session_rejected`、`upstream_event_rejected`、`upstream_unavailable` です。上流のエラー本文は認証情報や入力の漏出を防ぐため端末に転送しません。

端末から許可するイベントは上記に加えて `input_audio_buffer.clear` のみです。追加フィールド、`session.update`、指示文、ツール、モデル変更は拒否します。

## 参考

- [OpenAI Realtime conversations / Push-to-talk](https://developers.openai.com/api/docs/guides/realtime-conversations#push-to-talk)
- [OpenAI Python Realtime接続](https://developers.openai.com/api/reference/python/resources/realtime/methods/connect)
