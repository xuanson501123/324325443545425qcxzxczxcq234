import os, json, asyncio, subprocess
from keep_alive import keep_alive
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, CallbackQueryHandler, ConversationHandler
)

# === Cấu hình ===
BOT_TOKEN = "7905209230:AAF-AnSHZWih_7VYa_7VhkSPn7epyn3whIU"
AUTHORIZED_IDS = [5252425303, 6172090155]
REPO_PATH = ""
JSON_FILE = "index/accounts.json"
GIT_COMMIT_MESSAGE = "Cập nhật UDID: "

# === Trạng thái cho ConversationHandler ===
WAITING_CUSTOM_DAYS = 1

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
        subprocess.run(["git", "stash"], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        subprocess.run(["git", "stash", "pop"], check=True)
    except subprocess.CalledProcessError:
        print("⚠️ Gặp lỗi khi stash hoặc pull. Thử tiếp tục...")

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

# Nhận UDID từ user
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Không có quyền.")
        return

    udid = update.message.text.strip().upper()
    if not udid:
        await update.message.reply_text("⚠️ UDID không hợp lệ.")
        return

    context.user_data["udid"] = udid  # Lưu tạm UDID

    keyboard = [
        [InlineKeyboardButton("1 day", callback_data="days_1")],
        [InlineKeyboardButton("31 days", callback_data="days_31")],
        [InlineKeyboardButton("1000 days", callback_data="days_1000")],
        [InlineKeyboardButton("Tùy chỉnh", callback_data="custom_days")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(f"📌 Chọn thời hạn cho UDID: {udid}", reply_markup=reply_markup)

# Xử lý chọn nút
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    udid = context.user_data.get("udid")

    if not udid:
        await query.edit_message_text("⚠️ Không tìm thấy UDID. Hãy gửi lại.")
        return

    if query.data.startswith("days_"):
        days = int(query.data.split("_")[1])
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

        data = load_udid_data()
        data[udid] = expiry
        save_udid_data(data)
        git_commit_and_push(GIT_COMMIT_MESSAGE + udid)

        await query.edit_message_text(
            f"✅ Đã duyệt UDID: {udid}\n📅 Hạn dùng: {expiry}\n⏱️ Chờ 3-5 phút có thể sử dụng Mod."
        )

    elif query.data == "custom_days":
        await query.edit_message_text("✏️ Nhập số ngày bạn muốn cấp:")
        return WAITING_CUSTOM_DAYS

# Nhập số ngày tùy chỉnh
async def custom_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Vui lòng nhập số nguyên hợp lệ.")
        return WAITING_CUSTOM_DAYS

    udid = context.user_data.get("udid")
    if not udid:
        await update.message.reply_text("⚠️ Không tìm thấy UDID. Hãy gửi lại.")
        return ConversationHandler.END

    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    data = load_udid_data()
    data[udid] = expiry
    save_udid_data(data)
    git_commit_and_push(GIT_COMMIT_MESSAGE + udid)

    await update.message.reply_text(
        f"✅ Đã duyệt UDID: {udid}\n📅 Hạn dùng: {expiry}\n⏱️ Chờ 3-5 phút có thể sử dụng Mod."
    )
    return ConversationHandler.END

# /delete udid
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

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            WAITING_CUSTOM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_days)]
        },
        fallbacks=[],
        map_to_parent={}
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete", delete_udid))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_callback))

    print("✅ Bot đang chạy...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    keep_alive()
    print("✅ Server đang chạy...")
    asyncio.get_event_loop().run_until_complete(main())
