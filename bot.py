import telebot
from telebot import types
import sqlite3
import datetime
import threading
import os
import qrcode
from flask import Flask

# Core Configuration
BOT_TOKEN = "8893379598:AAEiQjFGVK2ek5-j7J0WD7B7suxqLySKxOg"
ADMIN_ID = 8213077389
MERCHANT_UPI = "paytm.s2wyw5w@pty"

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
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            name TEXT,
            price INTEGER DEFAULT 0,
            FOREIGN KEY(server_id) REFERENCES servers(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            file_id TEXT,
            file_type TEXT,
            caption TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            product_id INTEGER,
            chat_id INTEGER,
            price INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id INTEGER,
            product_id INTEGER,
            chat_id INTEGER,
            price INTEGER,
            screenshot_file_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchase_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            server_name TEXT,
            product_name TEXT,
            purchased_at TEXT
        )
    ''')
    conn.commit()
    
    # Insert default servers if empty
    cursor.execute("SELECT COUNT(*) FROM servers")
    if cursor.fetchone()[0] == 0:
        default_servers = [
            "insta viral aft", 
            "YouTubers Viral aft", 
            "actress viral aft", 
            "Trending Poem Videos", 
            "Trending Viral Leak aft"
        ]
        for s in default_servers:
            cursor.execute("INSERT OR IGNORE INTO servers (name) VALUES (?)", (s,))
        conn.commit()
        
    conn.close()

init_db()

# ----------------- KEYBOARD MARKUPS (2-PER-ROW LAYOUT) -----------------
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM servers")
    servers = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    i = 0
    while i < len(servers):
        row = []
        row.append(types.KeyboardButton(servers[i]))
        i += 1
        if i < len(servers):
            row.append(types.KeyboardButton(servers[i]))
            i += 1
        markup.row(*row)
        
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("Admin Panel"))
    return markup

def get_admin_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product"),
        types.InlineKeyboardButton("📝 Edit Product", callback_data="admin_edit_product"),
        types.InlineKeyboardButton("❌ Delete Product", callback_data="admin_delete_product"),
        types.InlineKeyboardButton("📁 Add Content or Link", callback_data="admin_add_content"),
        types.InlineKeyboardButton("✏️ Edit Content or Link", callback_data="admin_edit_content"),
        types.InlineKeyboardButton("🗑️ Delete Content or Link", callback_data="admin_delete_content"),
        types.InlineKeyboardButton("📋 List Content / Buyers", callback_data="admin_list_content"),
        types.InlineKeyboardButton("💳 Payment Approvals", callback_data="admin_payment_approvals"),
        types.InlineKeyboardButton("🧹 Clear Content List (2M+)", callback_data="admin_clear_content"),
        types.InlineKeyboardButton("📊 View Stats", callback_data="admin_stats"),
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
        "Welcome to the bot.\n"
        "Please select any Server from the keyboard below to explore."
    )
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_orders WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    user_states.pop(user_id, None)
    send_welcome_message(message.chat.id, message.from_user)

# ----------------- DEDICATED SCREENSHOT HANDLER FOR USERS -----------------
@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id].get("action") == "waiting_for_payment_screenshot", content_types=['photo', 'document', 'text'])
def handle_user_screenshot_direct(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text and message.text == "Admin Panel":
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.text:
        file_id = message.text

    if not file_id:
        bot.send_message(chat_id, "⚠️ Please send payment screenshot.")
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, product_id, price FROM pending_orders WHERE user_id = ?", (user_id,))
    order = cursor.fetchone()

    if not order:
        conn.close()
        user_states.pop(user_id, None)
        bot.send_message(chat_id, "⚠️ No active order found. Please select product again.")
        return

    order_id, prod_id, price = order
    cursor.execute("INSERT INTO pending_approvals (order_id, user_id, product_id, chat_id, price, screenshot_file_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (order_id, user_id, prod_id, chat_id, price, file_id))
    cursor.execute("DELETE FROM pending_orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()

    user_states.pop(user_id, None)
    bot.send_message(chat_id, "⏳ *Screenshot Received!*\n\nYour payment screenshot has been sent to Admin for approval. Please wait...", parse_mode="Markdown")

    # Notify Admin
    cursor_a = sqlite3.connect("bot_database.db").cursor()
    cursor_a.execute("SELECT name FROM products WHERE id = ?", (prod_id,))
    p_name = cursor_a.fetchone()[0]

    admin_msg = (
        f"🔔 *New Payment Approval Request!*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"📦 Product: *{p_name}*\n"
        f"💰 Amount: `₹{price}`\n"
        f"🆔 Order ID: `{order_id}`"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{user_id}"),
        types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_pay_{user_id}")
    )
    try:
        bot.send_photo(ADMIN_ID, file_id, caption=admin_msg, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup, parse_mode="Markdown")

# ----------------- GENERAL TEXT HANDLERS -----------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "Admin Panel" and user_id == ADMIN_ID:
        bot.send_message(chat_id, "🔧 *Admin Control Panel:*", reply_markup=get_admin_inline(), parse_mode="Markdown")
        return

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM servers WHERE name = ?", (text,))
    server = cursor.fetchone()
    
    if server:
        cursor.execute("DELETE FROM pending_orders WHERE user_id = ?", (user_id,))
        user_states.pop(user_id, None)
        conn.commit()

        server_id = server[0]
        cursor.execute("SELECT id, name, price FROM products WHERE server_id = ?", (server_id,))
        products = cursor.fetchall()
        conn.close()

        if not products:
            bot.send_message(chat_id, f"🌐 *Server: {text}*\n\nAbhi is server mein koi Products add nahi kiye gaye hain!", parse_mode="Markdown")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in products:
            markup.add(types.InlineKeyboardButton(f"📦 {p[1]} - ₹{p[2]}", callback_data=f"buy_prod_{p[0]}"))
        bot.send_message(chat_id, f"🌐 *Server: {text}*\n\nSelect a Product below to buy:", reply_markup=markup, parse_mode="Markdown")
    else:
        conn.close()
        if user_id == ADMIN_ID and user_id in user_states:
            handle_admin_text_states(message)

def handle_admin_text_states(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    text = message.text.strip()
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    if state["action"] == "adding_product":
        try:
            parts = text.split(",")
            p_name = parts[0].strip()
            p_price = int(parts[1].strip())
            server_id = state["server_id"]
            
            cursor.execute("INSERT INTO products (server_id, name, price) VALUES (?, ?, ?)", (server_id, p_name, p_price))
            conn.commit()
            bot.send_message(message.chat.id, f"✅ Product *{p_name}* (₹{p_price}) added successfully!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, "❌ Invalid format! Use: `ProductName,Price` (e.g. `VIP Pack,150`)", parse_mode="Markdown")
        user_states.pop(user_id, None)

    elif state["action"] == "editing_product":
        try:
            parts = text.split(",")
            p_name = parts[0].strip()
            p_price = int(parts[1].strip())
            prod_id = state["product_id"]
            
            cursor.execute("UPDATE products SET name = ?, price = ? WHERE id = ?", (p_name, p_price, prod_id))
            conn.commit()
            bot.send_message(message.chat.id, f"✅ Product updated to *{p_name}* (₹{p_price})!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, "❌ Invalid format! Use: `ProductName,Price`", parse_mode="Markdown")
        user_states.pop(user_id, None)

    elif state["action"] == "waiting_for_content":
        prod_id = state["product_id"]
        # Handle text / link input directly
        cursor.execute("INSERT INTO contents (product_id, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
                       (prod_id, text, "text", text))
        conn.commit()
        conn.close()
        user_states.pop(user_id, None)
        bot.send_message(message.chat.id, f"✅ Text / Link successfully added to product!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    elif state["action"] == "broadcasting":
        if text == "Finish Sending":
            user_states.pop(user_id, None)
            bot.send_message(message.chat.id, "✅ Broadcast completed.", reply_markup=get_main_keyboard(user_id))
            conn.close()
            return
            
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        success = 0
        for u in users:
            try:
                bot.copy_message(chat_id=u[0], from_chat_id=message.chat.id, message_id=message.message_id)
                success += 1
            except Exception:
                pass
        bot.send_message(message.chat.id, f"✅ Broadcast sent to {success} users!\n(Aur bhej sakte hain, ya 'Finish Sending' dabayein).")
        conn.close()
        return

    conn.close()

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.from_user.id in user_states, content_types=['photo', 'video', 'document'])
def handle_admin_media_states(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    
    if state["action"] == "waiting_for_content":
        prod_id = state["product_id"]
        file_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else message.video.file_id)
        file_type = "photo" if message.photo else ("document" if message.document else "video")
        caption = message.caption or ""

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO contents (product_id, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
                       (prod_id, file_id, file_type, caption))
        conn.commit()
        conn.close()

        user_states.pop(user_id, None)
        bot.send_message(message.chat.id, f"✅ Media successfully added to product!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ----------------- CALLBACK QUERY HANDLERS -----------------
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    user_id, chat_id, msg_id = call.from_user.id, call.message.chat.id, call.message.message_id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # --- BUY PRODUCT & QR GENERATION FLOW ---
    if call.data.startswith("buy_prod_"):
        prod_id = call.data.split("_")[2]
        cursor.execute("SELECT name, price, server_id FROM products WHERE id = ?", (prod_id,))
        p_data = cursor.fetchone()
        if not p_data:
            bot.answer_callback_query(call.id, "Product not found!", show_alert=True)
            conn.close()
            return
        
        p_name, price, s_id = p_data
        order_id = f"ORDER{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}{user_id}"
        
        upi_url = f"upi://pay?pa={MERCHANT_UPI}&pn=Aftab&am={price}&cu=INR&tn={order_id}"
        qr_img = qrcode.make(upi_url)
        qr_filename = f"qr_{user_id}.png"
        qr_img.save(qr_filename)
        
        cursor.execute("DELETE FROM pending_orders WHERE user_id = ?", (user_id,))
        cursor.execute("INSERT INTO pending_orders (order_id, user_id, product_id, chat_id, price) VALUES (?, ?, ?, ?, ?)",
                       (order_id, user_id, prod_id, chat_id, price))
        conn.commit()
        conn.close()

        invoice_text = (
            f"💳 *Payment Invoice*\n\n"
            f"📦 Product: *{p_name}*\n"
            f"💰 Amount: `₹{price}`\n"
            f"🆔 Order ID: `{order_id}`\n\n"
            f"📌 *Instructions:*\n"
            f"1. Scan QR code and pay ₹{price}.\n"
            f"2. Send payment **Screenshot** here."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel Payment", callback_data=f"cancel_pay_{s_id}"))

        with open(qr_filename, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=invoice_text, reply_markup=markup, parse_mode="Markdown")
        
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
        os.remove(qr_filename)
        
        user_states[user_id] = {"action": "waiting_for_payment_screenshot"}
        return

    # --- CANCEL PAYMENT FLOW ---
    if call.data.startswith("cancel_pay_"):
        server_id = call.data.split("_")[2]
        cursor.execute("DELETE FROM pending_orders WHERE user_id = ?", (user_id,))
        conn.commit()
        user_states.pop(user_id, None)

        cursor.execute("SELECT name FROM servers WHERE id = ?", (server_id,))
        s_data = cursor.fetchone()
        server_name = s_data[0] if s_data else "Server"

        cursor.execute("SELECT id, name, price FROM products WHERE server_id = ?", (server_id,))
        products = cursor.fetchall()
        conn.close()

        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in products:
            markup.add(types.InlineKeyboardButton(f"📦 {p[1]} - ₹{p[2]}", callback_data=f"buy_prod_{p[0]}"))

        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

        bot.send_message(chat_id, f"❌ *Payment Cancelled.*\n\n🌐 *Server: {server_name}*\nSelect a Product below:", reply_markup=markup, parse_mode="Markdown")
        return

    # --- ADMIN PAYMENT APPROVALS FLOW ---
    if call.data.startswith("approve_pay_") or call.data.startswith("decline_pay_"):
        target_user_id = int(call.data.split("_")[2])
        is_approve = call.data.startswith("approve_pay_")

        cursor.execute("SELECT approval_id, order_id, product_id, chat_id FROM pending_approvals WHERE user_id = ?", (target_user_id,))
        approval = cursor.fetchone()

        if not approval:
            bot.answer_callback_query(call.id, "Request already processed or not found!", show_alert=True)
            conn.close()
            return

        app_id, order_id, prod_id, target_chat_id = approval
        cursor.execute("DELETE FROM pending_approvals WHERE approval_id = ?", (app_id,))
        
        cursor.execute("SELECT name, server_id FROM products WHERE id = ?", (prod_id,))
        p_info = cursor.fetchone()
        p_name, s_id = p_info
        cursor.execute("SELECT name FROM servers WHERE id = ?", (s_id,))
        server_name = cursor.fetchone()[0]

        if is_approve:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO purchase_logs (user_id, server_name, product_name, purchased_at) VALUES (?, ?, ?, ?)",
                           (target_user_id, server_name, p_name, current_time))
            conn.commit()
            
            # Fetch contents to deliver to user
            cursor.execute("SELECT file_id, file_type, caption FROM contents WHERE product_id = ?", (prod_id,))
            contents = cursor.fetchall()
            conn.close()

            bot.answer_callback_query(call.id, "✅ Payment Approved successfully!")
            bot.edit_message_caption("✅ *Payment Approved & Content Delivered!*", chat_id, msg_id, parse_mode="Markdown")
            
            bot.send_message(target_chat_id, f"✅ *Payment Successfully Verified & Approved!*\n\nHere is your product *{p_name}*:", parse_mode="Markdown")
            
            if not contents:
                bot.send_message(target_chat_id, "⚠️ No content files uploaded for this product yet. Contact Admin.")
            
            for file_id, file_type, caption in contents:
                try:
                    cap = caption if caption else ""
                    if file_type == 'photo':
                        bot.send_photo(target_chat_id, file_id, caption=cap)
                    elif file_type == 'video':
                        bot.send_video(target_chat_id, file_id, caption=cap)
                    elif file_type == 'document':
                        bot.send_document(target_chat_id, file_id, caption=cap)
                    else:
                        bot.send_message(target_chat_id, file_id)
                except Exception as e:
                    print(f"Error sending content: {e}")
        else:
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, "❌ Payment Declined!")
            bot.edit_message_caption("❌ *Payment Declined by Admin.*", chat_id, msg_id, parse_mode="Markdown")
            bot.send_message(target_chat_id, "❌ *Your payment was declined by Admin.*\nIf you think this is a mistake, contact support.", parse_mode="Markdown")
        return

    # --- ADMIN PANEL OPTIONS ---
    if call.data == "admin_payment_approvals":
        cursor.execute('''
            SELECT pending_approvals.user_id, pending_approvals.order_id, products.name, pending_approvals.price, users.name 
            FROM pending_approvals 
            JOIN products ON pending_approvals.product_id = products.id
            LEFT JOIN users ON pending_approvals.user_id = users.user_id
        ''')
        approvals = cursor.fetchall()
        if not approvals:
            bot.answer_callback_query(call.id, "No pending payments waiting for approval!", show_alert=True)
            conn.close()
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for a in approvals:
            u_name = a[4] or "User"
            markup.add(types.InlineKeyboardButton(f"👤 {u_name} | {a[2]} (₹{a[3]})", callback_data=f"view_app_{a[0]}"))
        markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
        bot.edit_message_text("💳 *Pending Payment Approvals:*", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("view_app_"):
        t_user_id = call.data.split("_")[2]
        cursor.execute('''
            SELECT pending_approvals.order_id, products.name, pending_approvals.price, pending_approvals.screenshot_file_id 
            FROM pending_approvals 
            JOIN products ON pending_approvals.product_id = products.id 
            WHERE pending_approvals.user_id = ?
        ''', (t_user_id,))
        app_data = cursor.fetchone()
        conn.close()

        if not app_data:
            bot.answer_callback_query(call.id, "Request not found!", show_alert=True)
            return

        order_id, p_name, price, f_id = app_data
        text = f"📦 Product: *{p_name}*\n💰 Price: `₹{price}`\n🆔 Order ID: `{order_id}`\n👤 User ID: `{t_user_id}`"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{t_user_id}"),
            types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_pay_{t_user_id}"),
            types.InlineKeyboardButton("⇦ Back", callback_data="admin_payment_approvals")
        )
        try:
            bot.send_photo(chat_id, f_id, caption=text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, text + "\n\n(Screenshot could not be loaded)", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_add_product":
        cursor.execute("SELECT id, name FROM servers")
        servers = cursor.fetchall()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for s in servers:
            markup.add(types.InlineKeyboardButton(s[1], callback_data=f"add_prod_srv_{s[0]}"))
        markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
        bot.edit_message_text("Select Server to add Product:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("add_prod_srv_"):
        server_id = call.data.split("_")[3]
        user_states[user_id] = {"action": "adding_product", "server_id": server_id}
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "➕ Type Product Name and Price in format:\n`ProductName,Price` (e.g. `VIP Access,199`)", parse_mode="Markdown")

    elif call.data == "admin_edit_product":
        cursor.execute("SELECT id, name, price FROM products")
        prods = cursor.fetchall()
        if not prods:
            bot.answer_callback_query(call.id, "No products available to edit!", show_alert=True)
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for p in prods:
                markup.add(types.InlineKeyboardButton(f"{p[1]} (₹{p[2]})", callback_data=f"edit_prod_{p[0]}"))
            markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
            bot.edit_message_text("Select Product to Edit:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("edit_prod_"):
        prod_id = call.data.split("_")[2]
        user_states[user_id] = {"action": "editing_product", "product_id": prod_id}
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "✏️ Type new Name and Price in format:\n`NewName,Price` (e.g. `Ultra Pack,299`)", parse_mode="Markdown")

    elif call.data == "admin_delete_product":
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        if not prods:
            bot.answer_callback_query(call.id, "No products available to delete!", show_alert=True)
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for p in prods:
                markup.add(types.InlineKeyboardButton(f"❌ {p[1]}", callback_data=f"del_prod_{p[0]}"))
            markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
            bot.edit_message_text("Select Product to Delete:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("del_prod_"):
        prod_id = call.data.split("_")[2]
        cursor.execute("DELETE FROM contents WHERE product_id = ?", (prod_id,))
        cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ Product deleted successfully!", show_alert=True)
        bot.edit_message_text("🔧 *Admin Control Panel:*", chat_id, msg_id, reply_markup=get_admin_inline(), parse_mode="Markdown")
        return

    elif call.data == "admin_add_content":
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        if not prods:
            bot.answer_callback_query(call.id, "No products available!", show_alert=True)
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for p in prods:
                markup.add(types.InlineKeyboardButton(p[1], callback_data=f"add_cont_to_{p[0]}"))
            markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
            bot.edit_message_text("Select Product to add content/video/link:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("add_cont_to_"):
        prod_id = call.data.split("_")[3]
        user_states[user_id] = {"action": "waiting_for_content", "product_id": prod_id}
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "📁 Ab is product ke liye video, photo, document ya text link bhejein:")

    elif call.data == "admin_delete_content":
        cursor.execute('''
            SELECT contents.id, products.name, contents.file_type 
            FROM contents JOIN products ON contents.product_id = products.id
        ''')
        contents = cursor.fetchall()
        if not contents:
            bot.answer_callback_query(call.id, "No content available to delete!", show_alert=True)
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for c in contents:
                markup.add(types.InlineKeyboardButton(f"❌ [{c[1]}] ID: {c[0]} ({c[2]})", callback_data=f"del_c_{c[0]}"))
            markup.add(types.InlineKeyboardButton("⇦ Back", callback_data="back_to_admin"))
            bot.edit_message_text("Select Content to Delete:", chat_id, msg_id, reply_markup=markup)

    elif call.data.startswith("del_c_"):
        c_id = call.data.split("_")[2]
        cursor.execute("DELETE FROM contents WHERE id = ?", (c_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ Content deleted successfully!", show_alert=True)
        bot.edit_message_text("🔧 *Admin Control Panel:*", chat_id, msg_id, reply_markup=get_admin_inline(), parse_mode="Markdown")
        return

    elif call.data == "admin_list_content":
        cursor.execute('''
            SELECT purchase_logs.user_id, purchase_logs.server_name, purchase_logs.product_name, purchase_logs.purchased_at, users.name 
            FROM purchase_logs 
            LEFT JOIN users ON purchase_logs.user_id = users.user_id
            ORDER BY purchase_logs.id DESC LIMIT 30
        ''')
        logs = cursor.fetchall()
        if not logs:
            bot.answer_callback_query(call.id, "No buyer history found!", show_alert=True)
            conn.close()
            return

        text = "📋 *Recent Buyer / Purchase Logs:*\n\n"
        for l in logs:
            u_name = l[4] or "Unknown"
            text += f"👤 *User:* {u_name} (`{l[0]}`)\n🌐 *Server:* {l[1]}\n📦 *Product:* {l[2]}\n🕒 *Time:* `{l[3]}`\n----------------------------------\n"
        
        if len(text) > 4000:
            text = text[:4000]
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=get_admin_inline(), parse_mode="Markdown")

    elif call.data == "admin_clear_content":
        two_months_ago = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT COUNT(*) FROM purchase_logs WHERE purchased_at < ?", (two_months_ago,))
        count = cursor.fetchone()[0]
        
        if count == 0:
            bot.answer_callback_query(call.id, "2 months se purani koi buyer list nahi mili!", show_alert=True)
        else:
            cursor.execute("DELETE FROM purchase_logs WHERE purchased_at < ?", (two_months_ago,))
            conn.commit()
            bot.answer_callback_query(call.id, f"✅ Cleaned! Total {count} old buyer logs removed.", show_alert=True)

    elif call.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        total_prods = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM purchase_logs")
        total_buyers = cursor.fetchone()[0]
        conn.close()
        bot.answer_callback_query(call.id, f"Users: {total_users} | Products: {total_prods} | Purchases: {total_buyers}", show_alert=True)

    elif call.data == "admin_broadcast":
        user_states[user_id] = {"action": "broadcasting"}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Finish Sending"))
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "📢 Send message/photo/video to broadcast to all users:", reply_markup=markup)

    elif call.data == "back_to_admin":
        user_states.pop(user_id, None)
        bot.edit_message_text("🔧 *Admin Control Panel:*", chat_id, msg_id, reply_markup=get_admin_inline(), parse_mode="Markdown")

    elif call.data == "admin_back_main":
        user_states.pop(user_id, None)
        bot.delete_message(chat_id, msg_id)
        
    conn.close()

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
