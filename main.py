import flet as ft
import sqlite3
from datetime import datetime
import socket
import threading
import json
import os
import shutil
import math


# ================= DATABASE =================

conn = sqlite3.connect("fletgram.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    name TEXT,
    avatar TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    online INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    name TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS members (
    chat_id TEXT,
    username TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    sender TEXT,
    text TEXT,
    time TEXT,
    is_read INTEGER DEFAULT 0,
    type TEXT DEFAULT 'text'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

conn.commit()

if not os.path.exists("avatars"):
    os.makedirs("avatars")


# ================= HELPERS =================

def now():
    return datetime.now().strftime("%H:%M")

def get_setting(key, default=None):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cur.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    conn.commit()

# ================= BUILT-IN SERVER =================

clients = {}  # username -> socket


def start_server():
    def handle_client(conn, addr):
        try:
            username = conn.recv(1024).decode()
            clients[username] = conn
            print(f"{username} подключился")

            while True:
                data = conn.recv(4096).decode()
                if not data:
                    break

                msg = json.loads(data)

                # рассылаем всем подключённым
                for user, client_conn in list(clients.items()):
                    try:
                        client_conn.send((json.dumps(msg) + "\n").encode())

                    except:
                        pass

        except Exception as e:
            print("Ошибка клиента:", e)

        finally:
            for user, client_conn in list(clients.items()):
                if client_conn == conn:
                    del clients[user]
            conn.close()

    def server_loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 5000))
        server.listen()
        print("Сервер запущен")

        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            ).start()

    threading.Thread(target=server_loop, daemon=True).start()


# ================= APP =================

async def main(page: ft.Page):

    page.title = "LoliGram"
    page.padding = 0
    saved_theme = get_setting("theme", "dark")
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    page.theme_mode = (
        ft.ThemeMode.DARK
        if saved_theme == "dark"
        else ft.ThemeMode.LIGHT
    )

    current_user = {"username": None, "name": None}
    current_chat = {"id": None}
    client_socket = None

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            set_setting("theme", "light")
        else:
            page.theme_mode = ft.ThemeMode.DARK
            set_setting("theme", "dark")

        page.update()

    def listen_server():
        nonlocal client_socket

        buffer = ""

        while True:
            try:
                data = client_socket.recv(4096).decode()
                if not data:
                    break

                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    if not line.strip():
                        continue

                    msg = json.loads(line)

                    cur.execute("""
                                INSERT INTO messages (chat_id, sender, text, time, is_read)
                                VALUES (?, ?, ?, ?, 0)
                                """, (
                                    msg["chat_id"],
                                    msg["sender"],
                                    msg["text"],
                                    msg["time"]
                                ))
                    conn.commit()

                    # 🔥 UI обновляем через event loop
                    page.run_task(update_ui, msg)

            except Exception as e:
                print("Ошибка listen:", e)
                break

    async def update_ui(msg):

        if current_chat["id"] == msg["chat_id"]:
            messages_view.controls.append(
                bubble(
                    cur.lastrowid,
                    msg["text"],
                    msg["sender"] == current_user["username"],
                    msg["time"],
                    0
                )
            )

            messages_view.update()

    def connect_to_server():
        nonlocal client_socket
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect(("127.0.0.1", 5000))

            client_socket.send(current_user["username"].encode())

            threading.Thread(target=listen_server, daemon=True).start()

            print("Подключено к серверу")

        except Exception as e:
            print("Ошибка подключения:", e)
            client_socket = None

    messages_view = ft.ListView(expand=True, spacing=10, padding=10)

    # ================= MESSAGE BUBBLE =================

    def delete_message(msg_id):
        cur.execute("DELETE FROM messages WHERE id=?", (msg_id,))
        conn.commit()
        show_chat()

    def bubble(msg_id, text, me, time, is_read):

        status = "✓✓" if me and is_read else "✓" if me else ""

        content = (
            ft.Image(text[4:], width=200)
            if text.startswith("img:")
            else ft.Text(text, color="white")
        )

        return ft.Row(
            alignment=ft.MainAxisAlignment.END if me else ft.MainAxisAlignment.START,
            controls=[
                ft.Container(
                    padding=12,
                    border_radius=16,
                    bgcolor=ft.colors.BLUE if me else ft.colors.GREY_800,
                    on_long_press=lambda e: delete_message(msg_id),
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            content,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                spacing=4,
                                controls=[
                                    ft.Text(time, size=10, color="white70"),
                                    ft.Text(status, size=12)
                                ]
                            )
                        ]
                    )
                )
            ]
        )

    # ================= LOGIN =================

    def show_login():
        page.clean()

        username = ft.TextField(label="Username (@username)", width=300)

        def login(e):
            cur.execute("SELECT name FROM users WHERE username=?", (username.value,))
            row = cur.fetchone()
            if not row:
                username.error_text = "Пользователь не найден"
                page.update()
                return

            current_user["username"] = username.value
            current_user["name"] = row[0]
            set_setting("last_user", username.value)

            cur.execute("UPDATE users SET online=1 WHERE username=?", (username.value,))
            conn.commit()

            show_chats()
            connect_to_server()

        page.add(
            ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                controls=[
                    ft.Text("FletGram", size=34, weight="bold"),
                    username,
                    ft.ElevatedButton("Войти", on_click=login, width=300),
                    ft.TextButton("Регистрация", on_click=lambda e: show_register())
                ]
            )
        )

    # ================= REGISTER =================

    def show_register():
        page.clean()

        name = ft.TextField(label="Имя", width=300)
        username = ft.TextField(label="Username (@username)", width=300)

        def register(e):
            if not username.value.startswith("@"):
                username.error_text = "Username должен начинаться с @"
                page.update()
                return

            cur.execute("SELECT username FROM users WHERE username=?", (username.value,))
            if cur.fetchone():
                username.error_text = "Username занят"
                page.update()
                return

            cur.execute("""
            INSERT INTO users (username,name,avatar,bio,online)
            VALUES (?,?,?,?,?)
            """, (username.value, name.value, "", "", 0))
            conn.commit()

            current_user["username"] = username.value
            current_user["name"] = name.value
            set_setting("last_user", username.value)

            show_chats()

        page.add(
            ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                controls=[
                    ft.Text("Регистрация", size=30, weight="bold"),
                    name,
                    username,
                    ft.ElevatedButton("Создать", on_click=register, width=300)

                ]
            )
        )

    # ================= CHATS =================

    def show_chats():
        page.clean()

        def open_chat(cid):
            current_chat["id"] = cid
            show_chat()

        cur.execute("""
                    SELECT c.id
                    FROM chats c
                             JOIN members m ON c.id = m.chat_id
                    WHERE m.username = ?
                    """, (current_user["username"],))

        chat_tiles = []

        for (cid,) in cur.fetchall():

            # получаем второго участника
            cur.execute(
                "SELECT username FROM members WHERE chat_id=?",
                (cid,)
            )
            members = [row[0] for row in cur.fetchall()]

            other_user = None
            for m in members:
                if m != current_user["username"]:
                    other_user = m
                    break

            if not other_user:
                other_user = current_user["username"]

            # получаем аватар
            cur.execute(
                "SELECT avatar FROM users WHERE username=?",
                (other_user,)
            )
            row = cur.fetchone()
            avatar_filename = row[0] if row and row[0] else None

            tile = ft.Container(
                content=ft.ListTile(
                    leading=ft.CircleAvatar(
                        radius=20,
                        content=ft.Image(
                            src=f"avatars/{avatar_filename}",
                            fit=ft.ImageFit.COVER
                        ) if avatar_filename else None
                    ),
                    title=ft.Text(other_user, weight="bold"),
                    on_click=lambda e, c=cid: open_chat(c)
                ),
                margin=ft.margin.symmetric(vertical=4, horizontal=8),  # маленький зазор
                border_radius=10,
            )

            chat_tiles.append(tile)

        page.add(
            ft.AppBar(
                title=ft.Text("Чаты"),
                actions=[
                    ft.IconButton(ft.icons.SEARCH, on_click=lambda e: show_search()),
                    ft.IconButton(ft.icons.SETTINGS, on_click=lambda e: show_settings()),
                    ft.IconButton(ft.icons.DARK_MODE, on_click=toggle_theme),
                ]
            ),
            ft.ListView(
                expand=True,
                spacing=4,
                padding=ft.padding.only(top=8),
                controls=chat_tiles
            )
        )

        page.update()

    # ================= CHAT =================

    def show_chat():
        page.clean()

        chat_id = current_chat["id"]

        # ---------- участники ----------
        cur.execute(
            "SELECT username FROM members WHERE chat_id=?",
            (chat_id,)
        )
        members = [row[0] for row in cur.fetchall()]

        other_user = next(
            (m for m in members if m != current_user["username"]),
            current_user["username"]
        )

        # ---------- аватар ----------
        cur.execute(
            "SELECT avatar FROM users WHERE username=?",
            (other_user,)
        )
        row = cur.fetchone()
        avatar_filename = row[0] if row and row[0] else None

        chat_avatar = ft.Container(
            content=ft.CircleAvatar(
                radius=18,
                content=ft.Image(
                    src=f"avatars/{avatar_filename}",
                    fit=ft.ImageFit.COVER
                ) if avatar_filename else None,
            ),
            on_click=lambda e: show_user_profile(other_user)
        )

        messages_view.controls.clear()

        # ---------- загрузка сообщений ----------
        cur.execute(
            "SELECT id, sender, text, time, is_read FROM messages WHERE chat_id=? ORDER BY id",
            (chat_id,)
        )

        for msg_id, sender, text, time, is_read in cur.fetchall():
            messages_view.controls.append(
                bubble(
                    msg_id,
                    text,
                    sender == current_user["username"],
                    time if time else "",
                    is_read
                )
            )

        # ---------- отправка ----------
        message_input = ft.TextField(
            hint_text="Сообщение...",
            expand=True,
            on_submit=lambda e: send_message()
        )

        def send_message():
            text = message_input.value.strip()
            if not text:
                return

            msg_time = now()

            cur.execute("""
                        INSERT INTO messages (chat_id, sender, text, time, is_read)
                        VALUES (?, ?, ?, ?, 0)
                        """, (
                            chat_id,
                            current_user["username"],
                            text,
                            msg_time
                        ))
            conn.commit()

            msg_id = cur.lastrowid

            # отправка в сервер
            if client_socket:
                client_socket.send(
                    (json.dumps({
                        "chat_id": chat_id,
                        "sender": current_user["username"],
                        "text": text,
                        "time": msg_time
                    }) + "\n").encode()
                )

            messages_view.controls.append(
                bubble(msg_id, text, True, msg_time, 0)
            )

            message_input.value = ""
            page.update()

        # ---------- UI ----------
        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.icons.ARROW_BACK,
                    on_click=lambda e: show_chats()
                ),
                title=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        chat_avatar,
                        ft.Text(other_user, weight="bold")
                    ]
                )
            ),
            messages_view,
            ft.Row(
                controls=[
                    message_input,
                    ft.IconButton(
                        ft.icons.SEND,
                        on_click=lambda e: send_message()
                    )
                ]
            )
        )

        page.update()

    # ================= SEARCH =================

    def show_search():
        page.clean()

        search_field = ft.TextField(label="Поиск по @username")
        results = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

        def search(e):
            results.controls.clear()
            query = search_field.value.strip()

            if not query.startswith("@"):
                query = "@" + query

            cur.execute("""
                        SELECT username, name
                        FROM users
                        WHERE LOWER(username) LIKE LOWER(?)
                           OR LOWER(name) LIKE LOWER(?)
                        """, (f"%{query}%", f"%{query}%"))

            for username, name in cur.fetchall():
                results.controls.append(
                    ft.ListTile(
                        title=ft.Text(username),
                        subtitle=ft.Text(name),
                        trailing=ft.Text(
                            "Это вы" if username == current_user["username"] else "",
                            color="green"


                        ),
                        on_click=lambda e, u=username: show_user_profile(u)
                    )
                )

            page.update()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(ft.icons.ARROW_BACK, on_click=lambda e: show_chats()),
                title=ft.Text("Поиск")
            ),
            search_field,
            ft.ElevatedButton("Найти", on_click=search),
            results
        )

    # ================= PROFILE =================

    def show_user_profile(username):
        page.clean()

        # Получаем данные пользователя
        cur.execute(
            "SELECT username, bio, avatar FROM users WHERE username=?",
            (username,)
        )
        user = cur.fetchone()

        if not user:
            return

        username, bio, avatar_filename = user

        # ---------- АВАТАР ----------
        avatar_image = ft.CircleAvatar(
            radius=60,
            content=ft.Image(
                src=f"avatars/{avatar_filename}",
                fit=ft.ImageFit.COVER
            ) if avatar_filename else None
        )

        # ---------- СМЕНА ФОТО ----------
        def change_photo(e):
            file_picker.pick_files(allow_multiple=False)

        def on_file_selected(e):
            if not e.files:
                return

            file = e.files[0]
            ext = os.path.splitext(file.name)[1]
            new_filename = f"{current_user['username'].replace('@', '')}{ext}"
            new_path = os.path.join("avatars", new_filename)

            shutil.copy(file.path, new_path)

            cur.execute(
                "UPDATE users SET avatar=? WHERE username=?",
                (new_filename, current_user["username"])
            )
            conn.commit()

            # Перезагружаем профиль
            show_user_profile(current_user["username"])

        file_picker.on_result = on_file_selected

        # ---------- КНОПКА НАПИСАТЬ ----------
        def open_chat(e):
            open_chat_with(username)

        def open_chat_with(target_username):
            user1 = current_user["username"]
            user2 = target_username

            # сортировка работает даже если user1 == user2
            u1, u2 = sorted([user1, user2])
            cid = f"private_{u1}_{u2}"

            cur.execute("SELECT id FROM chats WHERE id=?", (cid,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO chats VALUES (?,?)",
                    (cid, target_username)
                )

                cur.execute("INSERT INTO members VALUES (?,?)", (cid, u1))
                cur.execute("INSERT INTO members VALUES (?,?)", (cid, u2))
                conn.commit()

            current_chat["id"] = cid
            show_chat()

        # ---------- UI ----------
        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.icons.ARROW_BACK,
                    on_click=lambda e: show_chats()
                ),
                title=ft.Text("Профиль"),
            ),
            ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                spacing=15,
                controls=[
                    avatar_image,
                    ft.Text(username, size=22, weight="bold"),
                    ft.Text(bio if bio else "Без описания", italic=True),

                    # Если это чужой профиль
                    ft.ElevatedButton(
                        "Написать",
                        on_click=open_chat,
                    ),

                    # Если это свой профиль
                    ft.ElevatedButton(
                        "Сменить фото",
                        on_click=change_photo,
                        visible=username == current_user["username"]
                    ),

                    ft.Text(
                        "Это вы",
                        visible=username == current_user["username"]
                    ),
                ]
            )
        )

        page.update()

    # ================= SETTINGS =================

    def show_settings():
        page.clean()

        def logout(e):
            cur.execute(
                "UPDATE users SET online=0 WHERE username=?",
                (current_user["username"],)
            )
            conn.commit()
            set_setting("last_user", "")
            show_login()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.icons.ARROW_BACK,
                    on_click=lambda e: show_chats()
                ),
                title=ft.Text("Настройки"),
                actions=[
                    ft.IconButton(
                        ft.icons.DARK_MODE,
                        on_click=toggle_theme
                    )
                ]
            ),
            ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                spacing=20,
                controls=[
                    ft.ElevatedButton(
                        "Открыть профиль",
                        on_click=lambda e: show_user_profile(current_user["username"]),
                        width=250
                    ),
                    ft.ElevatedButton(
                        "Выйти",
                        on_click=logout,
                        width=250
                    )
                ]
            )
        )

        page.update()

    # ================= START =================

    last_user = get_setting("last_user")

    if last_user:
        cur.execute("SELECT name FROM users WHERE username=?", (last_user,))
        row = cur.fetchone()
        if row:
            current_user["username"] = last_user
            current_user["name"] = row[0]
            show_chats()
            connect_to_server()
            return
        # если автологина нет — показываем логин
    show_login()


if __name__ == "__main__":
    start_server()
    ft.app(target=main)

