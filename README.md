# obs-kunii-timer

OBS Studio 用のストップウォッチ & YouTube チャットオーバーレイです。

---

## ファイル構成

```
obs-kunii-timer/
├── start_system.command # ワンクリック起動スクリプト（Mac）
├── chat_server.py       # WebSocket サーバー（タイマー制御 + YouTube チャット取得）
├── timer_overlay.html   # OBS ブラウザソース用タイマーオーバーレイ
├── timer_control.html   # タイマー操作パネル（ブラウザで開く）
├── chat_overlay.html    # OBS ブラウザソース用チャットオーバーレイ
├── .env                 # APIキー・チャンネルID設定（.gitignore 対象）
└── logs/                # チャットログ保存先（.gitignore 対象）
```

---

## チャット & タイマー（chat_server.py + HTML オーバーレイ）

YouTube Live のチャットをリアルタイム表示しながら、ストップウォッチをブラウザ操作できるシステムです。

### 構成

```
YouTube Live（任意）
    ↓ pytchat
chat_server.py ──→ WebSocket (ws://localhost:8765) ──→ timer_overlay.html（OBS ブラウザソース）
    ↓                                               ├──→ timer_control.html（手元ブラウザタブ）
logs/...（チャットあり時）                          └──→ chat_overlay.html（OBS ブラウザソース）
```

### 動作環境

- Python 3.8 以上
- `pip install pytchat websockets`

### セットアップ（初回のみ）

仮想環境の使用を推奨します。

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install pytchat websockets
```

YouTube ライブ動画IDの**自動取得**を使う場合は `.env` を作成します。

```
YOUTUBE_API_KEY=your_api_key_here
YOUTUBE_CHANNEL_ID=UCxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` を置かなくても起動時に URL を手動入力するか、引数で渡すことができます。

### 使い方

**0. OBS を起動する**

```bash
open -a OBS   # OBS を起動（Mac）
```

**1. サーバーを起動する**

`start_system.command` をダブルクリックします（仮想環境の有効化と `chat_server.py` の起動を一括で行います）。

手動で起動する場合:

```bash
source venv/bin/activate
python chat_server.py
```

起動時の動作は以下の優先順位で決まります。

1. **引数あり** → 指定した URL のチャットを取得
2. **`.env` 設定あり** → ライブ中・配信予約の一覧を表示して選択
   ```
   配信が見つかりました:
     1. 【サッカー】vsチームA  [LIVE]
     2. 練習配信              [予約済み]
   番号を選択 (1-2 / 0でスキップ):
   ```
3. **配信が見つからない / 0でスキップ** → URL 入力プロンプト（Enter でスキップするとタイマーのみモード）

```bash
# 引数で直接 URL を渡すこともできます
python chat_server.py "https://www.youtube.com/watch?v=xxxxxx"
```

**2. タイマー操作パネルを開く**

`timer_control.html` をブラウザで開きます（ローカルファイルをダブルクリックするか、ファイル URL で開く）。

| ボタン | 動作 |
|--------|------|
| キックオフ / 再開 | タイマーを開始・再開する |
| 一時停止 | タイマーを一時停止する |
| リセット | タイマーを停止して `00:00` に戻す |
| 時刻を同期 | 分・秒を入力して任意の時刻にセットする |
| チャット開始 | タイマーのみモードで起動後に YouTube チャットを後から有効にする |

> タイマーのみモードで起動した場合、操作パネルに **YouTube URL 入力欄**が表示されます。URL を入力して「チャット開始」を押すとチャット取得が始まり、入力欄は自動的に非表示になります。

**3. OBS にブラウザソースを追加する**

| ファイル | 用途 | 推奨サイズ |
|----------|------|------------|
| `timer_overlay.html` | タイマー表示（左上） | キャンバスと同解像度（例: 1920 × 1080） |
| `chat_overlay.html`  | チャット表示（右下） | キャンバスと同解像度（例: 1920 × 1080） |

OBS でソース追加 → 「ブラウザ」→「ローカルファイル」にチェックを入れてファイルを選択します。

**4. 確認**

- `timer_overlay.html` のインジケーターが **CONNECTED（緑）** になれば接続成功
- `chat_overlay.html` のインジケーター表示:
  - **CONNECTED（緑）** — YouTube チャットあり・接続中
  - **CHAT OFF（ピンク）** — タイマーのみモードで起動中（チャットなし）
  - **OFFLINE（ピンク）** — サーバー未起動または切断中
- タイマーステータス: 動作中は `LIVE`、停止中は `BREAK`（1 秒ごとに点滅）

### 注意

- `chat_server.py` と OBS を同じマシンで起動してください（デフォルト: `ws://localhost:8765`）。
- ログは `logs/` フォルダに自動保存されます（`.gitignore` 対象）。
- `chat_server.py` を再起動するとタイマーはリセットされます。

