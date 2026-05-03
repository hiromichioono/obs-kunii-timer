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
from concurrent.futures import ThreadPoolExecutor

# --- ログ設定 ---
now = datetime.datetime.now()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs", now.strftime('%Y'), now.strftime('%Y_%m'))
os.makedirs(LOG_DIR, exist_ok=True)
filename = os.path.join(LOG_DIR, f"chat_log_{now.strftime('%Y%m%d_%H%M')}.txt")

# --- WebSocket クライアント管理 ---
connected_clients = set()
chat_enabled = False  # YouTube URL ありで起動した場合 True

# --- タイマー状態 ---
timer_active = False
timer_start  = None   # float: time.time()
timer_offset = 0.0    # 一時停止前までの累積秒数
current_half = "前半"  # "前半" | "後半"

# --- 解説コンテンツ ---
commentary = {"score": "", "flow": "", "player": "", "term": ""}

# --- スコア ---
score = {"home": "", "away": "", "home_goals": 0, "away_goals": 0}


def get_timer_seconds() -> float:
    if timer_active and timer_start is not None:
        return timer_offset + (time.time() - timer_start)
    return timer_offset


def handle_command(action: str, seconds: float = 0) -> None:
    global timer_active, timer_start, timer_offset
    if action == "start" and not timer_active:
        timer_start = time.time()
        timer_active = True
    elif action == "stop" and timer_active:
        timer_offset += time.time() - timer_start
        timer_active = False
        timer_start = None
    elif action == "reset":
        timer_active = False
        timer_start = None
        timer_offset = 0.0
    elif action == "sync":
        timer_offset = float(seconds)
        if timer_active:
            timer_start = time.time()


async def broadcast(message: str):
    clients = list(connected_clients)  # イテレート中の変更を避けるためスナップショット
    if clients:
        await asyncio.gather(
            *[ws.send(message) for ws in clients],
            return_exceptions=True,
        )


def _timer_state_msg() -> str:
    return json.dumps({
        "type":    "timer",
        "seconds": int(get_timer_seconds()),
        "active":  timer_active,
        "chat":    chat_enabled,
        "half":    current_half,
        **score,
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
            if os.path.basename(self.path.split("?")[0]).startswith("."):
                self.send_error(403)
                return
            super().do_GET()

    handler = functools.partial(_SilentHandler, directory=BASE_DIR)
    with http.server.HTTPServer(("0.0.0.0", 8080), handler) as httpd:
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
                os.environ.setdefault(key.strip(), val.strip())


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
    global chat_enabled
    if chat_enabled:
        return
    chat_enabled = True
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
        chat_enabled = False
        await broadcast_timer_state()
        if os.path.exists(filename) and os.path.getsize(filename) == 0:
            os.remove(filename)
            print("メッセージなし。ログファイルを削除しました。")


async def handler(websocket):
    global current_half, commentary, score
    connected_clients.add(websocket)
    print(f"クライアント接続 (合計: {len(connected_clients)})")
    # 接続直後に現在の状態を送信（新規クライアントのみ）
    await websocket.send(_timer_state_msg())
    await websocket.send(json.dumps({"type": "commentary", **commentary}))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "cmd":
                    action = data["action"]
                    if action == "set_half":
                        current_half = data.get("half", "前半")
                        await broadcast_timer_state()
                    elif action == "set_teams":
                        score["home"] = data.get("home", "")
                        score["away"] = data.get("away", "")
                        await broadcast_timer_state()
                    elif action == "goal":
                        team = data.get("team", "")
                        if team == "home":
                            score["home_goals"] += 1
                        elif team == "away":
                            score["away_goals"] += 1
                        await broadcast_timer_state()
                    elif action == "undo_goal":
                        team = data.get("team", "")
                        if team == "home" and score["home_goals"] > 0:
                            score["home_goals"] -= 1
                        elif team == "away" and score["away_goals"] > 0:
                            score["away_goals"] -= 1
                        await broadcast_timer_state()
                    elif action == "start_chat":
                        video_id = data.get("video_id", "").strip()
                        if not video_id:
                            url = data.get("url", "").strip()
                            video_id = extract_video_id(url) if url else ""
                        if video_id and not chat_enabled:
                            asyncio.create_task(start_chat(video_id))
                    elif action == "set_commentary":
                        field = data.get("field", "")
                        if field in commentary:
                            commentary[field] = data.get("value", "")
                            await broadcast(json.dumps({"type": "commentary", **commentary}))
                    elif action == "get_streams":
                        items = fetch_streams()
                        await websocket.send(json.dumps({"type": "streams", "items": items}))
                    else:
                        handle_command(action, data.get("seconds", 0))
                        await broadcast_timer_state()
            except (json.JSONDecodeError, KeyError):
                pass
    finally:
        connected_clients.discard(websocket)
        print(f"クライアント切断 (合計: {len(connected_clients)})")


# --- pytchat チャット取得（別スレッドで実行）---
def fetch_chat(chat, loop: asyncio.AbstractEventLoop, log_file):
    while chat.is_alive():
        for c in chat.get().sync_items():
            amount = getattr(c, 'amountValue', 0)
            currency = getattr(c, 'currency', '')

            if amount:
                log_line = f"[{c.datetime}] 💰{c.author.name} ({currency}{amount}): {c.message}\n"
            else:
                log_line = f"[{c.datetime}] {c.author.name}: {c.message}\n"
            print(log_line, end="")
            log_file.write(log_line)
            log_file.flush()

            payload = {
                "author": c.author.name,
                "message": c.message or "",
                "datetime": c.datetime,
            }
            if amount:
                payload["superchat"] = {"amount": amount, "currency": currency}

            message = json.dumps(payload, ensure_ascii=False)
            asyncio.run_coroutine_threadsafe(broadcast(message), loop)


async def main(video_id: str | None):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: (print("\n✅ 記録を終了しました。") or os._exit(0)))

    hostname = socket.gethostname()
    threading.Thread(target=_start_http, daemon=True).start()

    async with websockets.serve(handler, "0.0.0.0", 8765):
        print(f"WebSocketサーバー起動: ws://localhost:8765")
        print(f"タイマー操作（iPhone）: http://{hostname}:8080/timer_input.html")
        asyncio.create_task(timer_tick())

        if video_id is not None:
            asyncio.create_task(start_chat(video_id))
        else:
            print("タイマーのみモードで起動（チャットなし）")

        await asyncio.Future()  # 無限待機（チャット終了後もサーバーを維持）


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
        print("\n✅ 記録を終了しました。")
        os._exit(0)
