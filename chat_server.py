import asyncio
import signal
import socket
import websockets
import pytchat
import json
import datetime
import os
import sys
import time
import urllib.request
import urllib.parse
import threading
import http.server
import functools
import random
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

# --- 定数 ---
WS_PORT           = 8765  # WebSocket サーバーポート
HTTP_PORT         = 8080  # HTTP サーバーポート
CHAT_COOLDOWN     = 30    # 同一ユーザーの連投制限（秒）
CHAT_COLOR_COUNT  = 7     # チャット色の種類数
CHAT_COLORS = ["#00E676","#C6FF00","#AA00FF","#FF7043","#40C4FF","#FF80AB","#64FFDA"]

# --- ログ設定 ---
now = datetime.datetime.now()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs", now.strftime('%Y'), now.strftime('%Y_%m'))
os.makedirs(LOG_DIR, exist_ok=True)
filename = os.path.join(LOG_DIR, f"chat_log_{now.strftime('%Y%m%d_%H%M')}.txt")

# 起動時に空ログを掃除（前回の強制終了で残ったファイルを削除）
for _f in os.scandir(LOG_DIR):
    if _f.name.endswith(".txt") and _f.stat().st_size == 0:
        os.remove(_f.path)

SESSION_SALT = str(random.randint(0, 999999))


@dataclass
class AppState:
    # タイマー
    timer_active: bool = False
    timer_start: float | None = None
    timer_offset: float = 0.0
    current_half: str = "前半"  # "前半" | "後半"
    # スコア
    score: dict = field(default_factory=lambda: {"home": "", "away": "", "home_goals": 0, "away_goals": 0})
    # 解説コンテンツ
    commentary: dict = field(default_factory=lambda: {"score": "", "flow": "", "player": "", "term": ""})
    # チャット・接続管理
    chat_enabled: bool = False
    connected_clients: set = field(default_factory=set)
    last_message_time: dict = field(default_factory=dict)
    seen_channels: set = field(default_factory=set)    # 初コメ検出
    pin_state: dict | None = None                       # ピン留めコメント
    comment_counts: dict = field(default_factory=dict)  # コメント数集計
    total_comments: int = 0                             # 配信全体コメント総数


state = AppState()


def is_total_milestone(count: int) -> bool:
    """配信全体コメント総数のマイルストーン判定"""
    if count < 50:
        return count % 10 == 0   # 10, 20, 30, 40
    if count < 200:
        return count % 50 == 0   # 50, 100, 150, 200
    if count < 1000:
        return count % 100 == 0  # 300, 400 ... 900, 1000
    return count % 500 == 0      # 1500, 2000 ...


def is_comment_milestone(count: int) -> bool:
    """序盤ボーナス・サッカー特別数（11）・キリ番でマイルストーン判定"""
    if count in {3, 11}:   # 序盤ボーナス + サッカー特別数
        return True
    if count < 20:
        return count % 5 == 0   # 5, 10, 15, 20
    if count < 100:
        return count % 10 == 0  # 20, 30, 40 ... 90
    return count % 50 == 0      # 100, 150, 200 ...


def get_timer_seconds() -> float:
    if state.timer_active and state.timer_start is not None:
        return state.timer_offset + (time.time() - state.timer_start)
    return state.timer_offset


def handle_command(action: str, seconds: float = 0) -> None:
    if action == "start" and not state.timer_active:
        state.timer_start = time.time()
        state.timer_active = True
    elif action == "stop" and state.timer_active:
        state.timer_offset += time.time() - state.timer_start
        state.timer_active = False
        state.timer_start = None
    elif action == "reset":
        state.timer_active = False
        state.timer_start = None
        state.timer_offset = 0.0
    elif action == "sync":
        state.timer_offset = float(seconds)
        if state.timer_active:
            state.timer_start = time.time()


async def broadcast(message: str):
    clients = list(state.connected_clients)  # イテレート中の変更を避けるためスナップショット
    if clients:
        await asyncio.gather(
            *[ws.send(message) for ws in clients],
            return_exceptions=True,
        )


def _timer_state_msg() -> str:
    return json.dumps({
        "type":    "timer",
        "seconds": int(get_timer_seconds()),
        "active":  state.timer_active,
        "chat":    state.chat_enabled,
        "half":    state.current_half,
        **state.score,
    })


async def broadcast_timer_state():
    await broadcast(_timer_state_msg())


async def timer_tick():
    while True:
        await asyncio.sleep(1)
        await broadcast_timer_state()


def _start_http():
    class _SilentHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if os.path.basename(path).startswith(".") or path.lstrip("/").startswith("logs/"):
                self.send_error(403)
                return
            super().do_GET()

    handler = functools.partial(_SilentHandler, directory=BASE_DIR)
    with http.server.HTTPServer(("0.0.0.0", HTTP_PORT), handler) as httpd:
        httpd.serve_forever()


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def fetch_streams() -> list[dict]:
    """ライブ中・配信予約の動画一覧を返す"""
    api_key    = os.environ.get("YOUTUBE_API_KEY")
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not api_key or not channel_id:
        return []
    results = []
    for event_type in ("live", "upcoming"):
        params = urllib.parse.urlencode({
            "part": "id,snippet",
            "channelId": channel_id,
            "eventType": event_type,
            "type": "video",
            "key": api_key,
        })
        try:
            with urllib.request.urlopen(
                f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=10
            ) as res:
                data = json.loads(res.read())
            for item in data.get("items", []):
                results.append({
                    "video_id": item["id"]["videoId"],
                    "title":    item["snippet"]["title"],
                    "live":     event_type == "live",
                })
        except Exception as e:
            print(f"配信情報取得エラー ({event_type}): {e}")
    return results


def extract_video_id(url: str) -> str:
    return url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]


async def start_chat(video_id: str):
    if state.chat_enabled:
        return
    state.chat_enabled = True
    await broadcast_timer_state()
    loop = asyncio.get_running_loop()
    try:
        chat = pytchat.create(video_id=f"https://www.youtube.com/watch?v={video_id}")
        print(f"チャット開始: {video_id}, ログ: {filename}")
        with open(filename, "a", encoding="utf-8") as f:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                await loop.run_in_executor(executor, fetch_chat, chat, loop, f)
            except asyncio.CancelledError:
                chat.terminate()
                raise
            finally:
                executor.shutdown(wait=False)
    except Exception as e:
        print(f"チャットエラー: {e}")
    finally:
        state.chat_enabled = False
        await broadcast_timer_state()
        if os.path.exists(filename) and os.path.getsize(filename) == 0:
            os.remove(filename)
            print("メッセージなし。ログファイルを削除しました。")


async def handler(websocket):
    state.connected_clients.add(websocket)
    print(f"クライアント接続 (合計: {len(state.connected_clients)})")
    # 接続直後に現在の状態を送信（新規クライアントのみ）
    await websocket.send(_timer_state_msg())
    await websocket.send(json.dumps({"type": "commentary", **state.commentary}))
    if state.pin_state is not None:
        await websocket.send(json.dumps({"type": "pin_chat", "data": state.pin_state}, ensure_ascii=False))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "cmd":
                    action = data["action"]
                    if action == "set_half":
                        state.current_half = data.get("half", "前半")
                        await broadcast_timer_state()
                    elif action == "set_teams":
                        state.score["home"] = data.get("home", "")
                        state.score["away"] = data.get("away", "")
                        await broadcast_timer_state()
                    elif action == "goal":
                        team = data.get("team", "")
                        if team == "home":
                            state.score["home_goals"] += 1
                        elif team == "away":
                            state.score["away_goals"] += 1
                        await broadcast_timer_state()
                    elif action == "undo_goal":
                        team = data.get("team", "")
                        if team == "home" and state.score["home_goals"] > 0:
                            state.score["home_goals"] -= 1
                        elif team == "away" and state.score["away_goals"] > 0:
                            state.score["away_goals"] -= 1
                        await broadcast_timer_state()
                    elif action == "start_chat":
                        video_id = data.get("video_id", "").strip()
                        if not video_id:
                            url = data.get("url", "").strip()
                            video_id = extract_video_id(url) if url else ""
                        if video_id and not state.chat_enabled:
                            asyncio.create_task(start_chat(video_id))
                    elif action == "set_commentary":
                        fname = data.get("field", "")
                        if fname in state.commentary:
                            state.commentary[fname] = data.get("value", "")
                            await broadcast(json.dumps({"type": "commentary", **state.commentary}))
                    elif action == "get_streams":
                        loop = asyncio.get_running_loop()
                        items = await loop.run_in_executor(None, fetch_streams)
                        await websocket.send(json.dumps({"type": "streams", "items": items}))
                    elif action == "anim_goal":
                        await broadcast(json.dumps({"type": "anim_goal"}))
                    elif action == "pin_chat":
                        pin_data = data.get("data")
                        if pin_data and "bg_color" not in pin_data:
                            ci = pin_data.get("color_index")
                            idx = (ci if ci is not None else 0) % CHAT_COLOR_COUNT
                            pin_data["bg_color"] = CHAT_COLORS[idx]
                        state.pin_state = pin_data
                        await broadcast(json.dumps({"type": "pin_chat", "data": pin_data}, ensure_ascii=False))
                    elif action == "test_comment":
                        msg = {"type": "chat_candidate", "author": "テスト太郎", "message": data.get("message", "テストコメントです！"), "datetime": str(datetime.datetime.now()), "color_index": random.randint(0, 6)}
                        await broadcast(json.dumps(msg, ensure_ascii=False))
                    elif action == "test_superchat":
                        amount = int(data.get("amount", 500))
                        msg = {"type": "chat_candidate", "author": "テスト太郎", "message": data.get("message", f"テストスパチャ {amount}円！"), "datetime": str(datetime.datetime.now()), "color_index": 0, "superchat": {"amount": amount, "currency": "¥"}}
                        await broadcast(json.dumps(msg, ensure_ascii=False))
                    else:
                        handle_command(action, data.get("seconds", 0))
                        await broadcast_timer_state()
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"メッセージ処理エラー: {e}")
    finally:
        state.connected_clients.discard(websocket)
        print(f"クライアント切断 (合計: {len(state.connected_clients)})")


# --- pytchat チャット取得（別スレッドで実行）---
def fetch_chat(chat, loop: asyncio.AbstractEventLoop, log_file):
    owner_id = os.environ.get("YOUTUBE_CHANNEL_ID", "")
    while chat.is_alive():
        for c in chat.get().sync_items():
            amount = getattr(c, 'amountValue', 0)
            currency = getattr(c, 'currency', '')
            channel_id = c.author.channelId
            is_superchat = bool(amount)
            is_owner = bool(owner_id) and channel_id == owner_id

            # 連投対策（スパチャ・配信者は免除）
            if not is_superchat and not is_owner:
                now_ts = time.time()
                if channel_id in state.last_message_time and now_ts - state.last_message_time[channel_id] < CHAT_COOLDOWN:
                    continue
                state.last_message_time[channel_id] = now_ts

            # 初コメ検出
            if channel_id not in state.seen_channels:
                state.seen_channels.add(channel_id)
                first_msg = f"👋 {c.author.name}さん、コメントありがとう！"
                asyncio.run_coroutine_threadsafe(
                    broadcast(json.dumps({"type": "stats", "message": first_msg}, ensure_ascii=False)), loop
                )

            # コメント数マイルストーン（個人）
            state.comment_counts[channel_id] = state.comment_counts.get(channel_id, 0) + 1
            count = state.comment_counts[channel_id]
            if is_comment_milestone(count):
                milestone_msg = f"🏆 {c.author.name}さん、{count}コメ達成！熱い応援ありがとう！"
                asyncio.run_coroutine_threadsafe(
                    broadcast(json.dumps({"type": "stats", "message": milestone_msg}, ensure_ascii=False)), loop
                )

            # コメント総数マイルストーン（配信全体）→ ticker へ
            state.total_comments += 1
            if is_total_milestone(state.total_comments):
                total_msg = f"🎉 配信コメント{state.total_comments}件突破！みんなありがとう！"
                asyncio.run_coroutine_threadsafe(
                    broadcast(json.dumps({"type": "ticker_alert", "message": total_msg}, ensure_ascii=False)), loop
                )

            color_index = int(hashlib.md5((channel_id + SESSION_SALT).encode()).hexdigest(), 16) % CHAT_COLOR_COUNT

            if amount:
                log_line = f"[{c.datetime}] 💰{c.author.name} ({currency}{amount}): {c.message}\n"
            else:
                log_line = f"[{c.datetime}] {c.author.name}: {c.message}\n"
            print(log_line, end="")
            log_file.write(log_line)
            log_file.flush()

            payload = {
                "type": "chat_candidate",
                "author": c.author.name,
                "message": c.message or "",
                "datetime": c.datetime,
                "color_index": color_index,
            }
            if amount:
                payload["superchat"] = {"amount": amount, "currency": currency}

            message = json.dumps(payload, ensure_ascii=False)
            asyncio.run_coroutine_threadsafe(broadcast(message), loop)


async def main(video_id: str | None):
    loop = asyncio.get_running_loop()

    def _on_sigint():
        print("\n✅ 記録を終了しました。", flush=True)
        os._exit(0)

    loop.add_signal_handler(signal.SIGINT, _on_sigint)

    hostname = socket.gethostname()
    threading.Thread(target=_start_http, daemon=True).start()

    async with websockets.serve(handler, "0.0.0.0", WS_PORT):
        print(f"WebSocketサーバー起動: ws://localhost:{WS_PORT}")
        print(f"タイマー操作（iPhone）: http://{hostname}:{HTTP_PORT}/timer_input.html")
        asyncio.create_task(timer_tick())

        if video_id is not None:
            asyncio.create_task(start_chat(video_id))
        else:
            print("タイマーのみモードで起動（チャットなし）")

        await asyncio.Future()  # Ctrl+C まで待機（_on_sigint で終了）


if __name__ == "__main__":
    load_env()
    try:
        if len(sys.argv) > 1:
            video_id = extract_video_id(sys.argv[1])
        else:
            streams = fetch_streams()
            if streams:
                print("配信が見つかりました:")
                for i, s in enumerate(streams, 1):
                    label = "[LIVE]" if s["live"] else "[予約済み]"
                    print(f"  {i}. {s['title']}  {label}")
                video_id = None
                while True:
                    choice = input(f"番号を選択 (1-{len(streams)} / 0でスキップ): ").strip()
                    if choice == "0":
                        break
                    if choice.isdigit() and 1 <= int(choice) <= len(streams):
                        video_id = streams[int(choice) - 1]["video_id"]
                        break
                    print("無効な入力です。再入力してください。")
            else:
                url = input("URLを入力 (Enterでスキップ): ").strip()
                video_id = extract_video_id(url) if url else None

        asyncio.run(main(video_id))
    except KeyboardInterrupt:
        print("\n✅ 記録を終了しました。")  # signal handler 未対応環境のフォールバック
