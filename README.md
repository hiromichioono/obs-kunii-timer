# obs-kunii-timer

OBS Studio 用のストップウォッチ & YouTube チャットオーバーレイです。

---

## ファイル構成

```
obs-kunii-timer/
├── chat_server.py       # WebSocket サーバー（タイマー制御 + YouTube チャット取得）
├── timer_overlay.html   # OBS ブラウザソース用タイマーオーバーレイ
├── timer_control.html   # タイマー操作パネル（ブラウザで開く）
├── chat_overlay.html    # OBS ブラウザソース用チャットオーバーレイ
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

### 使い方

**0. OBS と仮想環境を起動する**

```bash
open -a OBS                 # OBS を起動（Mac）
source venv/bin/activate    # 仮想環境を有効化
```

**1. サーバーを起動する**

```bash
python chat_server.py
```

起動すると YouTube URL の入力を求められます。**Enter でスキップするとタイマーのみモード**で起動します（チャットなし）。URL を入力するとチャット取得も有効になります。

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

