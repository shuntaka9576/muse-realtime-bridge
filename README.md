# Muse Realtime Bridge

M5Stack StopWatchとOpenAI Realtime APIをつなぐ音声中継プログラムの開発用リポジトリです。

MuseのVM上で中継プログラムを動かし、StopWatchから音声会話できる構成を目指します。必要に応じてMuseへの作業依頼も連携する想定です。

## 想定構成

```text
M5Stack StopWatch（マイク・スピーカー・ボタン）
    ↕ 音声・操作イベント
Muse VM（このリポジトリの中継プログラム）
    ↕ 音声・会話イベント
OpenAI Realtime API
```

端末側の変更は [muse-gadget-sdk](https://github.com/shuntaka9576/muse-gadget-sdk) で管理します。

## 現在の状態

設計前の初期状態です。実行可能な中継プログラムやセットアップスクリプトはまだありません。

実装前に次を確認します。

- StopWatchからMuse VM内の自作プロセスへ接続する経路
- VMで利用できるランタイムとプロセスの常駐方法
- 音声形式、ボタン操作、割り込み、切断時の処理
- OpenAI APIキーのVM側での設定方法
- Museへ作業を依頼し、結果を受け取る方法

Muse標準の `/voice/realtime` を変更するものではありません。独自の中継を設置する構成を検証します。

## Museへのセットアップ依頼について

将来的には、このリポジトリのURLとセットアップ手順をMuseへ渡し、VMへの導入を依頼できる形にします。現時点では導入手順が未実装のため、クローンだけでは動作しません。

APIキーやトークンなどの認証情報をコミットしないでください。
