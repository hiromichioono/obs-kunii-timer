import asyncio
import websockets
import pytchat
import json
import datetime
import os
import sys
import time
import urllib.request
import urllib.parse
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
    if connected_clients:
        await asyncio.gather(
            *[ws.send(message) for ws in connected_clients],
            return_exceptions=True,
        )


async def broadcast_timer_state():
    msg = json.dumps({"type": "timer", "seconds": int(get_timer_seconds()), "active": timer_active, "chat": chat_enabled})
    await broadcast(msg)


async def timer_tick():
    while True:
        await asyncio.sleep(1)
        await broadcast_timer_state()


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


def fetch_live_video_id() -> str | None:
    api_key    = os.environ.get("YOUTUBE_API_KEY")
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if not api_key or not channel_id:
        return None
    params = urllib.parse.urlencode({
        "part": "id",
        "channelId": channel_id,
        "eventType": "live",
        "type": "video",
        "key": api_key,
    })
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=10) as res:
            data = json.loads(res.read())
        items = data.get("items", [])
        return items[0]["id"]["videoId"] if items else None
    except Exception as e:
        print(f"ライブ動画ID取得エラー: {e}")
        return None


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
            with ThreadPoolExecutor(max_workers=1) as executor:
                try:
                    await loop.run_in_executor(executor, fetch_chat, chat, loop, f)
                except asyncio.CancelledError:
                    chat.terminate()
                    raise
    except Exception as e:
        print(f"チャットエラー: {e}")
    finally:
        chat_enabled = False
        await broadcast_timer_state()


async def handler(websocket):
    connected_clients.add(websocket)
    print(f"クライアント接続 (合計: {len(connected_clients)})")
    # 接続直後に現在のタイマー状態を送信
    await websocket.send(json.dumps({"type": "timer", "seconds": int(get_timer_seconds()), "active": timer_active, "chat": chat_enabled}))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "cmd":
                    action = data["action"]
                    if action == "start_chat":
                        url = data.get("url", "").strip()
                        if url and not chat_enabled:
                            asyncio.create_task(start_chat(extract_video_id(url)))
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
    async with websockets.serve(handler, "localhost", 8765):
        print("WebSocketサーバー起動: ws://localhost:8765")
        asyncio.create_task(timer_tick())

        if video_id is not None:
            asyncio.create_task(start_chat(video_id))
        else:
            print("タイマーのみモードで起動（チャットなし）")

        await asyncio.Future()  # 無限待機（チャット終了後もサーバーを維持）


if __name__ == "__main__":
    load_env()
    if len(sys.argv) > 1:
        url = sys.argv[1]
        video_id = extract_video_id(url)
    else:
        print("ライブ動画IDを自動取得中...")
        video_id = fetch_live_video_id()
        if video_id:
            print(f"ライブ動画を検出: {video_id}")
        else:
            url = input("URLを入力 (Enterでスキップ): ").strip()
            video_id = extract_video_id(url) if url else None

    try:
        asyncio.run(main(video_id))
    except KeyboardInterrupt:
        print("\n✅ 記録を終了しました。")
