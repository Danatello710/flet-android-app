import flet as ft
import sqlite3
from datetime import datetime

# ================== DATABASE ==================

conn = sqlite3.connect("fletgram.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    name TEXT
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
    chat_id TEXT,
    sender TEXT,
    text TEXT,
    time TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

conn.commit()

# ================== STATE ==================

current_user = {"username": None, "name": None}
current_chat = {"id": None}

# ================== HELPERS ==================

def now():
    return datetime.now().strftime("%H:%M")

def center(content):
    return ft.Container(
        content=content,
        expand=True,
        alignment=ft.alignment.Alignment(0, 0),
    )

def get_setting(key, default=None):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cur.execute(
        "INSERT OR REPLACE INTO settings VALUES (?, ?)",
        (key, value)
    )
    conn.commit()

def bubble(text, me, time):
    return ft.Row(
        alignment=ft.MainAxisAlignment.END if me else ft.MainAxisAlignment.START,
        controls=[
            ft.Container(
                padding=12,
                border_radius=16,
                bgcolor=ft.Colors.BLUE if me else ft.Colors.GREY_800,
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(text, color="white"),
                        ft.Text(time, size=10, color="white70"),
                    ],
                ),
            )
        ],
    )

# ================== APP ==================

async def main(page: ft.Page):
    page.title = "FletGram"
    page.padding = 0

    # ---- THEME ----
    saved_theme = get_setting("theme", "dark")
    page.theme_mode = (
        ft.ThemeMode.DARK if saved_theme == "dark"
        else ft.ThemeMode.LIGHT
    )

    messages = ft.ListView(expand=True, spacing=10, padding=12)

    # ================== SCREENS ==================

    def show_login():
        page.clean()
        username = ft.TextField(label="Username (@username)")

        def login(e):
            cur.execute(
                "SELECT name FROM users WHERE username=?",
                (username.value,)
            )
            row = cur.fetchone()
            if not row:
                username.error_text = "Пользователь не найден"
                page.update()
                return

            current_user["username"] = username.value
            current_user["name"] = row[0]
            set_setting("last_user", username.value)
            show_chats()

        page.add(
            center(
                ft.Column(
                    width=320,
                    spacing=20,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Вход", size=28, weight="bold"),
                        username,
                        ft.Button(content=ft.Text("Войти"), on_click=login, width=260),
                        ft.TextButton(
                            content=ft.Text("Регистрация"),
                            on_click=lambda e: show_register(),
                        ),

                    ],
                )
            )
        )

    def show_register():
        page.clean()

        name = ft.TextField(label="Имя")
        username = ft.TextField(label="Username (@username)")

        def register(e):
            if not username.value or not username.value.startswith("@"):
                username.error_text = "Username должен начинаться с @"
                page.update()
                return

            cur.execute(
                "SELECT username FROM users WHERE username=?",
                (username.value,)
            )
            if cur.fetchone():
                username.error_text = "Username занят"
                page.update()
                return

            cur.execute(
                "INSERT INTO users VALUES (?, ?)",
                (username.value, name.value)
            )
            conn.commit()

            current_user["username"] = username.value
            current_user["name"] = name.value
            set_setting("last_user", username.value)
            show_chats()

        page.add(
            center(
                ft.Column(
                    width=320,
                    spacing=20,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Регистрация", size=28, weight="bold"),
                        name,
                        username,
                        ft.Button(content=ft.Text("Продолжить"), on_click=register, width=260),
                    ],
                )
            )
        )

    def show_chats():
        page.clean()

        def open_chat(cid):
            current_chat["id"] = cid
            show_chat()

        cur.execute("""
        SELECT c.id, c.name FROM chats c
        JOIN members m ON c.id = m.chat_id
        WHERE m.username = ?
        """, (current_user["username"],))

        chat_tiles = [
            ft.ListTile(
                title=ft.Text(name, weight="bold"),
                on_click=lambda e, c=cid: open_chat(c),
            )
            for cid, name in cur.fetchall()
        ]

        page.add(
            ft.AppBar(
                title=ft.Text("Чаты"),
                actions=[
                    ft.IconButton(ft.Icons.SEARCH, on_click=lambda e: show_search()),
                    ft.IconButton(ft.Icons.SETTINGS, on_click=lambda e: show_settings()),
                ],
            ),
            ft.ListView(expand=True, controls=chat_tiles),
            ft.FloatingActionButton(
                icon=ft.Icons.GROUP_ADD,
                on_click=lambda e: show_create_group(),
            ),
        )

    def show_chat():
        page.clean()
        cid = current_chat["id"]

        cur.execute("SELECT name FROM chats WHERE id=?", (cid,))
        chat_name = cur.fetchone()[0]

        messages.controls.clear()
        cur.execute(
            "SELECT sender, text, time FROM messages WHERE chat_id=?",
            (cid,)
        )
        for sender, text, time in cur.fetchall():
            messages.controls.append(
                bubble(text, sender == current_user["username"], time)
            )

        field = ft.TextField(hint_text="Сообщение...", expand=True)

        def send(e):
            if not field.value:
                return
            t = now()
            cur.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?)",
                (cid, current_user["username"], field.value, t)
            )
            conn.commit()
            messages.controls.append(bubble(field.value, True, t))
            field.value = ""
            page.update()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda e: show_chats(),
                ),
                title=ft.Text(chat_name),
            ),
            messages,
            ft.Container(
                padding=12,
                content=ft.Row(
                    controls=[
                        field,
                        ft.IconButton(ft.Icons.SEND, on_click=send),
                    ]
                ),
            ),
        )

    def show_search():
        page.clean()
        query = ft.TextField(label="Поиск @username")
        results = ft.Column()

        def search(e):
            results.controls.clear()
            cur.execute(
                "SELECT username FROM users WHERE username LIKE ?",
                (f"%{query.value}%",)
            )
            for (u,) in cur.fetchall():
                if u != current_user["username"]:
                    results.controls.append(
                        ft.ListTile(
                            title=ft.Text(u),
                            on_click=lambda e, user=u: create_private_chat(user),
                        )
                    )
            page.update()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda e: show_chats(),
                ),
                title=ft.Text("Поиск"),
            ),
            query,
            ft.Button(content=ft.Text("Найти"), on_click=search),
            results,
        )

    def create_private_chat(user):
        cid = f"chat_{datetime.now().timestamp()}"
        cur.execute("INSERT INTO chats VALUES (?, ?)", (cid, user))
        cur.execute("INSERT INTO members VALUES (?, ?)", (cid, current_user["username"]))
        cur.execute("INSERT INTO members VALUES (?, ?)", (cid, user))
        conn.commit()
        current_chat["id"] = cid
        show_chat()

    def show_create_group():
        page.clean()
        name = ft.TextField(label="Название группы")

        def create(e):
            cid = f"group_{datetime.now().timestamp()}"
            cur.execute("INSERT INTO chats VALUES (?, ?)", (cid, name.value))
            cur.execute("INSERT INTO members VALUES (?, ?)", (cid, current_user["username"]))
            conn.commit()
            current_chat["id"] = cid
            show_chat()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda e: show_chats(),
                ),
                title=ft.Text("Новая группа"),
            ),
            name,
            ft.Button(content=ft.Text("Создать"), on_click=create),
        )

    def show_settings():
        page.clean()

        def toggle(e):
            page.theme_mode = (
                ft.ThemeMode.LIGHT
                if page.theme_mode == ft.ThemeMode.DARK
                else ft.ThemeMode.DARK
            )
            set_setting(
                "theme",
                "dark" if page.theme_mode == ft.ThemeMode.DARK else "light"
            )
            page.update()

        def logout(e):
            set_setting("last_user", "")
            current_user["username"] = None
            show_login()

        page.add(
            ft.AppBar(
                leading=ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda e: show_chats(),
                ),
                title=ft.Text("Настройки"),
            ),
            ft.ListTile(
                title=ft.Text("Тёмная тема"),
                trailing=ft.Switch(
                    value=page.theme_mode == ft.ThemeMode.DARK,
                    on_change=toggle,
                ),
            ),
            ft.ListTile(
                title=ft.Text("Выйти из аккаунта"),
                leading=ft.Icon(ft.Icons.LOGOUT),
                on_click=logout,
            ),
        )

    # ================== START ==================

    last_user = get_setting("last_user")
    if last_user:
        cur.execute("SELECT name FROM users WHERE username=?", (last_user,))
        row = cur.fetchone()
        if row:
            current_user["username"] = last_user
            current_user["name"] = row[0]
            show_chats()
            return

    show_login()


if __name__ == "__main__":
    ft.run(main)
