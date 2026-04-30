import asyncio
import websockets
import pytchat
import json
import datetime
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

# --- ログ設定 ---
now = datetime.datetime.now()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs", now.strftime('%Y'), now.strftime('%Y_%m'))
os.makedirs(LOG_DIR, exist_ok=True)
filename = os.path.join(LOG_DIR, f"chat_log_{now.strftime('%Y%m%d_%H%M')}.txt")

# --- WebSocket クライアント管理 ---
connected_clients = set()

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
    msg = json.dumps({"type": "timer", "seconds": int(get_timer_seconds()), "active": timer_active})
    await broadcast(msg)


async def timer_tick():
    while True:
        await asyncio.sleep(1)
        await broadcast_timer_state()


async def handler(websocket):
    connected_clients.add(websocket)
    print(f"クライアント接続 (合計: {len(connected_clients)})")
    # 接続直後に現在のタイマー状態を送信
    await websocket.send(json.dumps({"type": "timer", "seconds": int(get_timer_seconds()), "active": timer_active}))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "cmd":
                    handle_command(data["action"], data.get("seconds", 0))
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
            log_line = f"[{c.datetime}] {c.author.name}: {c.message}\n"
            print(log_line, end="")
            log_file.write(log_line)
            log_file.flush()

            message = json.dumps(
                {
                    "author": c.author.name,
                    "message": c.message,
                    "datetime": c.datetime,
                },
                ensure_ascii=False,
            )
            asyncio.run_coroutine_threadsafe(broadcast(message), loop)


async def main(video_id: str):
    loop = asyncio.get_running_loop()
    chat = pytchat.create(video_id=f"https://www.youtube.com/watch?v={video_id}")  # メインスレッドで生成（signal.signal制約のため）

    with open(filename, "a", encoding="utf-8") as f:
        print(f"ログ保存先: {filename}")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = loop.run_in_executor(executor, fetch_chat, chat, loop, f)

            async with websockets.serve(handler, "localhost", 8765):
                print("WebSocketサーバー起動: ws://localhost:8765")
                asyncio.create_task(timer_tick())
                await future


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("YouTube URLを入力: ")

    video_id = (
        url.split("v=")[-1].split("&")[0]
        if "v=" in url
        else url.split("/")[-1].split("?")[0]
    )

    try:
        asyncio.run(main(video_id))
    except KeyboardInterrupt:
        print("\n✅ 記録を終了しました。")
