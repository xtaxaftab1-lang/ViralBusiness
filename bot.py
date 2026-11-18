import telebot
from telebot import types
import sqlite3
import datetime
import threading
from flask import Flask

# Core Configuration
BOT_TOKEN = "8893379598:AAEiQjFGVK2ek5-j7J0WD7B7suxqLySKxOg"
ADMIN_ID = 8213077389

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# ----------------- DATABASE MANAGEMENT SYSTEM -----------------
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            join_date TEXT,
            status TEXT DEFAULT 'Active'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT,
            file_id TEXT,
            file_type TEXT,
            caption TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ----------------- KEYBOARD MARKUPS -----------------
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("insta viral aft"),
        types.KeyboardButton("YouTubers Viral aft")
    )
    markup.add(
        types.KeyboardButton("actress viral aft"),
        types.KeyboardButton("Trending Poem Videos")
    )
    markup.add(
        types.KeyboardButton("Trending Viral Leak aft")
    )
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("Admin Panel"))
    return markup

def get_admin_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Add Content / Post", callback_data="admin_add_post"),
        types.InlineKeyboardButton("📋 View Stats", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("⇦ Back to Main", callback_data="admin_back_main")
    )
    return markup

# ----------------- WELCOME HANDLER -----------------
def send_welcome_message(chat_id, user_info):
    user_id = user_info.id
    user_name = user_info.first_name or "User"
    username = f"@{user_info.username}" if user_info.username else "@None"
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT join_date FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, name, username, join_date, status) VALUES (?, ?, ?, ?, 'Active')", 
                       (user_id, user_name, username, current_date))
    else:
        cursor.execute("UPDATE users SET username = ?, name = ? WHERE user_id = ?", (username, user_name, user_id))
    conn.commit()
    conn.close()

    welcome_text = (
        f"👋 Hello *{user_name}*!\n\n"
        "Welcome to the channel content bot.\n"
        "Please select any category from the keyboard below to explore media."
    )
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    send_welcome_message(message.chat.id, message.from_user)

# ----------------- TEXT & CATEGORY HANDLER -----------------
@bot.message_handler(func=lambda message: message.text in [
    "insta viral aft", "YouTubers Viral aft", 
    "actress viral aft", "Trending Poem Videos", 
    "Trending Viral Leak aft"
])
def handle_categories(message):
    category_name = message.text
    chat_id = message.chat.id
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type, caption FROM posts WHERE category_name = ?", (category_name,))
    posts = cursor.fetchall()
    conn.close()

    if not posts:
        bot.send_message(chat_id, f"📂 *{category_name}*\n\nAbhi yahan koi content uploaded nahi hai. Admin jald hi add karega!", parse_mode="Markdown")
        return

    bot.send_message(chat_id, f"📂 *Showing items for: {category_name}*", parse_mode="Markdown")
    for file_id, file_type, caption in posts:
        try:
            cap = caption if caption else ""
            if file_type == 'photo':
                bot.send_photo(chat_id, file_id, caption=cap)
            elif file_type == 'video':
                bot.send_video(chat_id, file_id, caption=cap)
            elif file_type == 'document':
                bot.send_document(chat_id, file_id, caption=cap)
            else:
                bot.send_message(chat_id, file_id)
        except Exception as e:
            print(f"Error sending media: {e}")

@bot.message_handler(func=lambda message: message.text == "Admin Panel" and message.from_user.id == ADMIN_ID)
def admin_panel_handler(message):
    bot.send_message(message.chat.id, "🔧 *Admin Control Panel:*", reply_markup=get_admin_inline(), parse_mode="Markdown")

# ----------------- ADMIN BROADCAST / INPUT HANDLER -----------------
@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.from_user.id in user_states, content_types=['text', 'photo', 'video', 'document'])
def handle_admin_states(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    
    if state["action"] == "broadcasting":
        if message.text and message.text == "Finish Sending":
            user_states.pop(user_id, None)
            bot.send_message(message.chat.id, "✅ Broadcast completed.", reply_markup=get_main_keyboard(user_id))
            return
            
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        for u in users:
            try:
                bot.copy_message(chat_id=u[0], from_chat_id=message.chat.id, message_id=message.message_id)
                success += 1
            except Exception:
                pass
        bot.send_message(message.chat.id, f"✅ Broadcast sent to {success} users!\n(Aur bhej sakte hain, ya 'Finish Sending' dabayein).")

    elif state["action"] == "waiting_for_post":
        category = state["category"]
        file_id = None
        file_type = "text"
        caption = message.caption or message.text or ""

        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        elif message.video:
            file_id = message.video.file_id
            file_type = "video"
        elif message.document:
            file_id = message.document.file_id
            file_type = "document"
        else:
            file_id = message.text
            file_type = "text"

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO posts (category_name, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
                       (category, file_id, file_type, caption))
        conn.commit()
        conn.close()

        user_states.pop(user_id, None)
        bot.send_message(message.chat.id, f"✅ Content successfully added under *{category}*!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ----------------- CALLBACK QUERY HANDLER (ADMIN) -----------------
@bot.callback_query_handler(func=lambda call: True)
def handle_admin_callbacks(call):
    user_id, chat_id, msg_id = call.from_user.id, call.message.chat.id, call.message.message_id
    
    if call.data == "admin_stats":
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM posts")
        total_posts = cursor.fetchone()[0]
        conn.close()
        bot.answer_callback_query(call.id, f"Users: {total_users} | Posts: {total_posts}", show_alert=True)

    elif call.data == "admin_broadcast":
        user_states[user_id] = {"action": "broadcasting"}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Finish Sending"))
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "📢 Send message/photo/video to broadcast to all users:", reply_markup=markup)

    elif call.data == "admin_add_post":
        markup = types.InlineKeyboardMarkup(row_width=1)
        categories = [
            "insta viral aft", "YouTubers Viral aft", 
            "actress viral aft", "Trending Poem Videos", 
            "Trending Viral Leak aft"
        ]
        for cat in categories:
            markup.add(types.InlineKeyboardButton(cat, callback_data=f"select_cat_{cat}"))
        markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
        bot.edit_message_text("Select category to add post:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("select_cat_"):
        cat_name = call.data.replace("select_cat_", "")
        user_states[user_id] = {"action": "waiting_for_post", "category": cat_name}
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, f"📁 Send photo, video, document or text for *{cat_name}*:", parse_mode="Markdown")

    elif call.data == "back_to_admin":
        user_states.pop(user_id, None)
        bot.edit_message_text("🔧 *Admin Control Panel:*", chat_id, msg_id, reply_markup=get_admin_inline(), parse_mode="Markdown")

    elif call.data == "admin_back_main":
        user_states.pop(user_id, None)
        bot.delete_message(chat_id, msg_id)

# ----------------- FLASK SERVER FOR 24/7 HOSTING -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Viral Bot is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Bot polling started...", flush=True)
    bot.remove_webhook()
    bot.infinity_polling(timeout=50, long_polling_timeout=25)
