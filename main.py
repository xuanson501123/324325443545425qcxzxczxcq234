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
MAX_DAYS = 1000  # Giới hạn tối đa

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

def extend_expiry(udid, days):
    """Gia hạn hoặc thêm UDID mới"""
    data = load_udid_data()
    old_expiry = data.get(udid)
    new_expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    data[udid] = new_expiry
    save_udid_data(data)
    git_commit_and_push(GIT_COMMIT_MESSAGE + udid)
    return old_expiry, new_expiry

def delete_udid_by_value(udid):
    """Xoá UDID"""
    data = load_udid_data()
    if udid in data:
        del data[udid]
        save_udid_data(data)
        git_commit_and_push(f"Xoá UDID: {udid}")
        return True
    return False

# === Bot Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Gửi UDID để thêm hoặc chọn thời hạn bằng nút ➖➕⏪⏩.")

# Nhận UDID từ user
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Không có quyền.")
        return

    udid = update.message.text.strip().upper()
    if not udid:
        await update.message.reply_text("⚠️ UDID không hợp lệ.")
        return

    # Lưu UDID + số ngày mặc định
    context.user_data["udid"] = udid
    context.user_data["days"] = 31

    keyboard = [
        [InlineKeyboardButton("-30", callback_data="decrease_30"),
         InlineKeyboardButton("-7", callback_data="decrease_7"),
         InlineKeyboardButton("-1", callback_data="decrease_1"),
         InlineKeyboardButton("+1", callback_data="increase_1"),
         InlineKeyboardButton("+7", callback_data="increase_7"),
         InlineKeyboardButton("+30", callback_data="increase_30")],
        [InlineKeyboardButton("✅ Xác nhận", callback_data="confirm")],
        [InlineKeyboardButton("🗑 Xoá UDID", callback_data="delete_udid")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📌 UDID: {udid}\n📅 Thời hạn: {context.user_data['days']} ngày",
        reply_markup=reply_markup
    )

# Xử lý nút bấm
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    udid = context.user_data.get("udid")
    days = context.user_data.get("days", 7)

    if not udid:
        await query.edit_message_text("⚠️ Không tìm thấy UDID. Hãy gửi lại.")
        return

    # Tăng giảm số ngày
    if query.data.startswith("increase_") or query.data.startswith("decrease_"):
        step = int(query.data.split("_")[1])
        if query.data.startswith("increase_"):
            context.user_data["days"] = min(MAX_DAYS, days + step)
        else:
            context.user_data["days"] = max(1, days - step)

        new_days = context.user_data["days"]
        await query.edit_message_text(
            f"📌 UDID: {udid}\n📅 Thời hạn: {new_days} ngày",
            reply_markup=query.message.reply_markup
        )
        return
    # Xác nhận
    if query.data == "confirm":
        days = context.user_data["days"]
        old_expiry, new_expiry = extend_expiry(udid, days)
        if old_expiry:
            msg = f"🔄 UDID {udid} đã tồn tại\n📅 Hạn cũ: {old_expiry}\n➡️ Hạn mới: {new_expiry}"
        else:
            msg = f"✅ Đã duyệt UDID mới: {udid}\n📅 Hạn dùng: {new_expiry}"
        msg += "\n⏱️ Chờ 3-5 phút có thể sử dụng Mod."
        msg += "\nVideo hướng dẫn sử dụng mod Youtube: @tiptipmodios."

        await query.edit_message_text(msg, parse_mode="HTML")
        return


    # Xoá UDID
    if query.data == "delete_udid":
        if delete_udid_by_value(udid):
            await query.edit_message_text(f"🗑 Đã xoá UDID: {udid}")
        else:
            await query.edit_message_text("⚠️ Không tìm thấy UDID để xoá.")

# === Khởi chạy Bot ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={},
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
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