import os, json, asyncio, subprocess
from keep_alive import keep_alive
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# === Cấu hình ===
BOT_TOKEN = "7905209230:AAF-AnSHZWih_7VYa_7VhkSPn7epyn3whIU"
AUTHORIZED_IDS = [5252425303, 987654321]  # ✅ Thay bằng Telegram user ID thật của bạn
REPO_PATH = ""
JSON_FILE = "index/accounts.json"
GIT_COMMIT_MESSAGE = "Cập nhật UDID: "

# === Tạo thư mục nếu chưa có ===
os.makedirs(os.path.join(REPO_PATH, "index"), exist_ok=True)

# === Hàm tiện ích ===
def get_file_path():
    return os.path.join(REPO_PATH, JSON_FILE)

def load_udid_data():
    if os.path.exists(get_file_path()):
        with open(get_file_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_udid_data(data):
    with open(get_file_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
def git_commit_and_push(msg):
    token = os.getenv("GH_TOKEN")
    user = os.getenv("GH_USER")
    repo = os.getenv("GH_REPO")

    if not all([token, user, repo]):
        print("❌ Thiếu GH_TOKEN, GH_USER hoặc GH_REPO")
        return

    remote_url = f"https://{user}:{token}@github.com/{user}/{repo}.git"

    subprocess.run(["git", "config", "--global", "user.name", user], check=True)
    subprocess.run(["git", "config", "--global", "user.email", f"{user}@users.noreply.github.com"], check=True)
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

    try:
        # Stash thay đổi tạm thời (nếu có)
        subprocess.run(["git", "stash"], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        subprocess.run(["git", "stash", "pop"], check=True)
    except subprocess.CalledProcessError:
        print("⚠️ Gặp lỗi khi stash hoặc pull. Thử tiếp tục...")

    # Add + Commit + Push (force để tránh xung đột)
    try:
        subprocess.run(["git", "add", get_file_path()], check=True)
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "push", "--force", "origin", "main"], check=True)
        print("✅ Đã đẩy lên GitHub.")
    except subprocess.CalledProcessError as e:
        print("❌ Gặp lỗi khi push:", e)


def is_authorized(uid):
    return uid in AUTHORIZED_IDS

# === Bot Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Gửi UDID để thêm hoặc dùng /delete <udid> để xoá.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Không có quyền.")
        return

    udid = update.message.text.strip().upper()
    if not udid:
        await update.message.reply_text("⚠️ UDID không hợp lệ.")
        return

    data = load_udid_data()
    expiry = (datetime.now() + timedelta(days=31)).strftime("%Y-%m-%d")
    data[udid] = expiry
    save_udid_data(data)
    git_commit_and_push(GIT_COMMIT_MESSAGE + udid)
    await update.message.reply_text(f"✅ Đã thêm UDID: {udid}\n📅 Hạn dùng: {expiry}")

async def delete_udid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Không có quyền.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: /delete <udid>")
        return

    udid = context.args[0].strip().upper()
    data = load_udid_data()
    if udid in data:
        del data[udid]
        save_udid_data(data)
        git_commit_and_push(f"Xoá UDID: {udid}")
        await update.message.reply_text(f"🗑 Đã xoá {udid}")
    else:
        await update.message.reply_text("⚠️ Không tìm thấy UDID.")

# === Khởi chạy Bot ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete", delete_udid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot đang chạy...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    keep_alive()
    print("✅ Server đang chạy...")
    asyncio.get_event_loop().run_until_complete(main())
