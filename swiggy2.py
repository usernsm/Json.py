
import asyncio
import json
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BufferedInputFile
)

TOKEN = os.getenv("8698443936:AAFW5CDmXRQr3pIFxNTrrIhCcRrXqeoqcf4", "8698443936:AAFW5CDmXRQr3pIFxNTrrIhCcRrXqeoqcf4").strip()
BASE = Path.home() / ".json_manager_bot"
BASE.mkdir(parents=True, exist_ok=True)
DB = BASE / "records.db"

dp = Dispatcher()

FIELDS = [
    "name", "customerId", "mobile",
    "token", "tid", "sid", "deviceId"
]


def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                UNIQUE(user_id, fingerprint)
            )
        """)


def save_record(user_id, record):
    if not isinstance(record, dict):
        raise ValueError("Record must be a JSON object")

    missing = [key for key in FIELDS if key not in record]
    if missing:
        raise ValueError("Missing fields: " + ", ".join(missing))

    if not all(isinstance(record[key], str) for key in FIELDS):
        raise ValueError("All fields must contain strings")

    payload = json.dumps(record, ensure_ascii=False)
    fingerprint = json.dumps(
        {k: record[k] for k in FIELDS},
        sort_keys=True,
        ensure_ascii=False
    )

    with sqlite3.connect(DB) as con:
        cur = con.execute(
            """INSERT OR IGNORE INTO records
               (user_id, record_json, fingerprint)
               VALUES (?, ?, ?)""",
            (user_id, payload, fingerprint)
        )
        return cur.rowcount == 1


def get_records(user_id):
    with sqlite3.connect(DB) as con:
        rows = con.execute(
            """SELECT id, record_json FROM records
               WHERE user_id=? ORDER BY id""",
            (user_id,)
        ).fetchall()
    return [(row_id, json.loads(payload)) for row_id, payload in rows]


def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📄 Single JSON",
                callback_data="single"
            ),
            InlineKeyboardButton(
                text="📚 Bulk TXT",
                callback_data="bulk"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 My records",
                callback_data="list"
            ),
            InlineKeyboardButton(
                text="ℹ️ Help",
                callback_data="help"
            )
        ]
    ])


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🗂 <b>JSON Manager Bot</b>\n\n"
        "/addjson followed by a JSON object — save record\n"
        "/list — show record IDs\n"
        "/delete ID — delete one record\n\n"
        "Option 1 exports one record as JSON.\n"
        "Option 2 exports all records as a TXT file.",
        reply_markup=menu()
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Example format</b>\n"
        "<code>/addjson {\"name\":\"Test User\","
        "\"customerId\":\"TEST123\","
        "\"mobile\":\"9000000000\","
        "\"token\":\"TEST_TOKEN\","
        "\"tid\":\"TEST_TID\","
        "\"sid\":\"TEST_SID\","
        "\"deviceId\":\"TEST_DEVICE\"}</code>\n\n"
        "Use only records you are authorized to manage. "
        "Keep real authentication tokens private."
    )


@dp.message(Command("addjson"))
async def add_json(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: /addjson followed by a JSON object.\n"
            "Example: /addjson {\"name\":\"Test User\", ...}"
        )
        return

    try:
        record = json.loads(parts[1])
        inserted = save_record(message.from_user.id, record)
        if inserted:
            await message.answer("✅ Record saved.")
        else:
            await message.answer("ℹ️ Duplicate record; not added.")
    except (json.JSONDecodeError, ValueError) as exc:
        await message.answer(f"❌ Invalid record: {exc}")


@dp.message(Command("list"))
async def list_cmd(message: Message):
    records = get_records(message.from_user.id)
    if not records:
        await message.answer("No records saved yet.")
        return

    # IDs only: avoid exposing tokens in chat.
    lines = ["<b>Your records</b>"]
    for record_id, record in records:
        lines.append(
            f"ID <code>{record_id}</code> — "
            f"{record.get('name', 'Unnamed')} "
            f"(mobile: {record.get('mobile', '')})"
        )
    await message.answer("\n".join(lines), reply_markup=menu())


@dp.message(Command("delete"))
async def delete_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /delete 3")
        return

    with sqlite3.connect(DB) as con:
        cur = con.execute(
            "DELETE FROM records WHERE user_id=? AND id=?",
            (message.from_user.id, int(parts[1]))
        )

    await message.answer(
        "🗑 Record deleted." if cur.rowcount
        else "Record ID not found."
    )


@dp.callback_query(F.data == "list")
async def list_button(callback: CallbackQuery):
    records = get_records(callback.from_user.id)
    if not records:
        await callback.message.answer("No records saved yet.")
    else:
        await callback.message.answer(
            "\n".join(
                f"ID {rid} — {rec.get('name', 'Unnamed')}"
                for rid, rec in records
            )
        )
    await callback.answer()


@dp.callback_query(F.data == "single")
async def single_button(callback: CallbackQuery):
    records = get_records(callback.from_user.id)
    if not records:
        await callback.message.answer("Pehle /addjson se record add karo.")
    else:
        await callback.message.answer(
            "Single JSON ke liye record ID bhejo:\n"
            "Example: /export 1"
        )
    await callback.answer()


@dp.message(Command("export"))
async def export_one(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /export 1")
        return

    records = dict(get_records(message.from_user.id))
    record_id = int(parts[1])
    if record_id not in records:
        await message.answer("Record ID not found.")
        return

    data = json.dumps(
        records[record_id], ensure_ascii=False, indent=2
    ).encode("utf-8")

    file = BufferedInputFile(data, filename=f"record_{record_id}.json")
    await message.answer_document(
        file,
        caption="Single JSON export"
    )


@dp.callback_query(F.data == "bulk")
async def bulk_button(callback: CallbackQuery):
    records = get_records(callback.from_user.id)
    if not records:
        await callback.message.answer("Pehle /addjson se records add karo.")
        await callback.answer()
        return

    # JSON Lines format: each line is one complete JSON object.
    text = "\n".join(
        json.dumps(rec, ensure_ascii=False)
        for _, rec in records
    ) + "\n"

    file = BufferedInputFile(
        text.encode("utf-8"),
        filename="bulk_records.txt"
    )
    await callback.message.answer_document(
        file,
        caption=f"Bulk export: {len(records)} record(s)"
    )
    await callback.answer()


@dp.callback_query(F.data == "help")
async def help_button(callback: CallbackQuery):
    await callback.message.answer(
        "/addjson JSON — add record\n"
        "/list — list records\n"
        "/export ID — download one JSON\n"
        "/delete ID — delete record\n"
        "Bulk TXT — use the menu button"
    )
    await callback.answer()


async def main():
    if not TOKEN:
        raise SystemExit(
            "BOT_TOKEN missing.\n"
            "Run: export BOT_TOKEN='YOUR_BOT_TOKEN'"
        )

    init_db()
    bot = Bot(TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
