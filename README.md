# obs-kunii-timer

OBS Studio 用のストップウォッチ & YouTube チャットオーバーレイです。

---

## ファイル構成

```
obs-kunii-timer/
├── start_system.command      # ワンクリック起動スクリプト（Mac）
├── chat_server.py            # WebSocket サーバー（タイマー制御 + YouTube チャット取得）
├── timer_overlay.html        # OBS ブラウザソース用タイマーオーバーレイ
├── timer_input.html          # タイマー操作パネル（iPhone のブラウザで開く）
├── chat_overlay.html         # OBS ブラウザソース用チャットオーバーレイ
├── ticker_overlay.html       # OBS ブラウザソース用テロップオーバーレイ
├── ticker_messages.csv       # テロップメッセージ定義（編集可）
├── commentary_input.html     # 解説入力パネル（iPhone のブラウザで開く）
├── commentary_overlay.html   # OBS ブラウザソース用解説コンテンツオーバーレイ
├── test_chat.html            # チャット・スーパーチャット動作確認用テストパネル（開発用）
├── .env                      # APIキー・チャンネルID設定（.gitignore 対象）
├── project-tool-key_secret.json  # Google API OAuth2 認証ファイル（.gitignore 対象・未実装）
└── logs/                     # チャットログ保存先（.gitignore 対象）
```

---

## 画面構成

| 画面          | 用途                               |
| ------------- | ---------------------------------- |
| PC モニター 1 | 試合視聴 / OBS 出力確認            |
| PC モニター 2 | OBS 操作 / その他                  |
| iPhone        | `timer_input.html`（タイマー操作） |

---

## チャット & タイマー（chat_server.py + HTML オーバーレイ）

YouTube Live のチャットをリアルタイム表示しながら、ストップウォッチをブラウザ操作できるシステムです。

### 構成

```
YouTube Live（任意）
    ↓ pytchat
chat_server.py ──→ WebSocket ──→ timer_overlay.html      （OBS ブラウザソース）
    ↓                        ├──→ timer_input.html        （iPhone）
logs/...（チャットあり時）   ├──→ chat_overlay.html         （OBS ブラウザソース）
                             ├──→ ticker_overlay.html       （OBS ブラウザソース）
                             ├──→ commentary_overlay.html   （OBS ブラウザソース）
                             └──→ commentary_input.html     （ブラウザ）
```

### 動作環境

- Python 3.10 以上
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

`timer_input.html` をブラウザで開きます（ローカルファイルをダブルクリックするか、ファイル URL で開く）。

| ボタン / 入力         | 動作                                                                                                                         |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 前半 / 後半           | タイマーオーバーレイに表示するハーフラベルを切り替える（初期値: 前半）                                                       |
| キックオフ / 再開     | タイマーを開始・再開する                                                                                                     |
| 一時停止              | タイマーを一時停止する                                                                                                       |
| リセット              | タイマーを停止して `00:00` に戻す                                                                                            |
| 時刻を同期            | 分・秒を入力して任意の時刻にセットする                                                                                       |
| チーム名入力 + セット | ホーム・アウェイ名を入力して「セット」するとタイマーオーバーレイ中央にスコアが表示される。両方空欄でセットすると非表示になる |
| ＋ / − (得点)         | 各チームの得点を増減する                                                                                                     |
| ⚽ GOAL!!             | ゴールアニメーションを発火する                                                                                               |
| 配信一覧を取得        | タイマーのみモードで起動後に YouTube チャットを後から有効にする                                                              |

> タイマーのみモードで起動した場合、操作パネルに **「配信一覧を取得」ボタン**が表示されます。クリックすると配信一覧が表示され、選択するとチャット取得が始まります。チャット取得中はボタンが自動的に非表示になります。

**3. ブラウザパネルを開く**

`chat_server.py` 起動時に Terminal に表示される URL をブラウザで開きます。

```
タイマー操作（iPhone）: http://Hiro-Mac.local:8080/timer_input.html
```

解説入力パネルも同じホスト名でアクセスできます。

```
http://Hiro-Mac.local:8080/commentary_input.html
```

> iPhone は USB ケーブルでドッキングステーション経由で Mac に接続し、Safari で開いてください。設定変更は不要です。

解説入力パネルの各フィールドにテキストを入力して「送信」すると、`commentary_overlay.html` に即時反映されます。**入力欄を空欄にして送信すると、対応する項目がオーバーレイから非表示になります。**

**3b. テロップメッセージを編集する（任意）**

`ticker_messages.csv` をテキストエディタで直接編集します。

```csv
half,trigger_min,message
前半,0,キックオフ！前半が始まりました
後半,0,後半キックオフ！
break,0,ハーフタイム中です
```

| 列 | 内容 |
| ----------- | ------------------------------------------------------------ |
| `half` | `前半` / `後半` / `break` |
| `trigger_min` | 発火する分（整数）。`break` 行は `0`（値は無視される） |
| `message` | 表示テキスト |

- タイマーアクティブ時: 指定分ちょうどに1回だけ発火
- タイマー停止時（BREAK）: `break` 行のメッセージをスクロール終了後にループ表示
- テロップは**左から右**にスクロールします

> **注意:** テロップメッセージを編集する HTML 入力パネルは現時点では未実装です。`ticker_messages.csv` をテキストエディタで直接編集してください。編集後は OBS のブラウザソースを「再読み込み」してください。

**4. OBS にブラウザソースを追加する**

| ファイル                  | 用途                         | 推奨サイズ                              |
| ------------------------- | ---------------------------- | --------------------------------------- |
| `timer_overlay.html`      | タイマー表示（左上）         | キャンバスと同解像度（例: 1920 × 1080） |
| `chat_overlay.html`       | チャット表示（右下）         | キャンバスと同解像度（例: 1920 × 1080） |
| `ticker_overlay.html`     | テロップ表示（下部バー）     | キャンバスと同解像度（例: 1920 × 1080） |
| `commentary_overlay.html` | 解説コンテンツ表示（右上）   | キャンバスと同解像度（例: 1920 × 1080） |

OBS でソース追加 → 「ブラウザ」→「ローカルファイル」の**チェックを外し**、URL 欄に以下を入力します。

| ソース     | URL                                             |
| ---------- | ----------------------------------------------- |
| タイマー   | `http://localhost:8080/timer_overlay.html`      |
| チャット   | `http://localhost:8080/chat_overlay.html`       |
| テロップ   | `http://localhost:8080/ticker_overlay.html`     |
| 解説       | `http://localhost:8080/commentary_overlay.html` |

> `file://` ではなく HTTP URL を使う必要があります。`chat_server.py` 起動後に OBS ソースを更新してください。

**5. 確認**

- `timer_overlay.html` のインジケーターが **CONNECTED（緑）** になれば接続成功
- `chat_overlay.html` のインジケーター表示:
  - **CONNECTED（緑）** — YouTube チャットあり・接続中
  - **CHAT OFF（ピンク）** — タイマーのみモードで起動中（チャットなし）
  - **OFFLINE（ピンク）** — サーバー未起動または切断中
- `commentary_input.html` のインジケーターが **CONNECTED（緑）** になれば iPhone からの接続成功
- タイマーステータス: 動作中は `LIVE`、停止中は `BREAK`（1 秒ごとに点滅）

### 注意

- `chat_server.py` と OBS を同じマシンで起動してください。
- iPhone は USB ケーブル（ドッキングステーション経由可）で Mac と同じネットワーク上に置いてください。
- ログは `logs/` フォルダに自動保存されます（`.gitignore` 対象・HTTP アクセス不可）。チャットメッセージが0件の場合はファイルを自動削除します。
- `chat_server.py` を再起動するとタイマーはリセットされます。
- サーバーを終了するには Terminal で **Ctrl+C** を押してください。
- HTMLファイルを使用している場合は、OBS のブラウザソースのプロパティ画面で「再読み込み」をクリックしてください。

### チャット機能の詳細

**スーパーチャット**

スーパーチャットを自動検出し、`chat_overlay.html` に強調表示します。

**連投制限**

同一ユーザーのコメントは 30 秒間隔で制限されます。スーパーチャットと配信者（`YOUTUBE_CHANNEL_ID` と一致するチャンネル）は制限の対象外です。

**自動通知メッセージ**

| 種類 | 内容 | 表示先 |
| ---- | ---- | ------ |
| 初コメ歓迎 | `👋 {名前}さん、コメントありがとう！` | `chat_overlay.html` |
| 個人コメント数マイルストーン | 3・11（サッカー特別数）・5刻み（~19）・10刻み（20~99）・50刻み（100~）の節目で `🏆 {名前}さん、{N}コメ達成！` | `chat_overlay.html` |
| 配信全体コメント数マイルストーン | 10 件ごと（50 件以降は 50 刻み、200 件以降は 100 刻み、1000 件以降は 500 刻み）で `🎉 配信コメント{N}件突破！` | `ticker_overlay.html` |
