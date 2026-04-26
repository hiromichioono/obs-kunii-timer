import pytchat
import datetime
import os

# 実行ファイルの階層を基準にする書き方
now     = datetime.datetime.now()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs", now.strftime('%Y'), now.strftime('%Y_%m'))
os.makedirs(LOG_DIR, exist_ok=True)

video_url = input("YouTube URLを入力: ")
# v= の後を取得し、さらに & があればそれ以降を切り捨てる
video_id = video_url.split("v=")[-1].split("&")[0] if "v=" in video_url else video_url.split("/")[-1].split("?")[0]
chat = pytchat.create(video_id=video_id)

filename = os.path.join(LOG_DIR, f"chat_log_{now.strftime('%Y%m%d_%H%M')}.txt")

print(f"🚀 記録開始！ ログ保存先: {filename}")

with open(filename, "a", encoding="utf-8") as f:
    try:
        while chat.is_alive():
            for c in chat.get().sync_items():
                log_line = f"[{c.datetime}] {c.author.name}: {c.message}\n"
                print(log_line, end="")
                f.write(log_line)
                f.flush()
    except KeyboardInterrupt:
        print("\n✅ 記録を終了しました。")