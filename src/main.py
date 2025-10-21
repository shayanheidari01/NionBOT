from rubpy.bot import BotClient, filters
from rubpy.bot.models import Update
from dotenv import load_dotenv
import os
import random
import re
import aiohttp
import aiosqlite
import json

from strings import get_string
from database import init_db, async_session
from database import crud, models
from sqlalchemy import select
from keyboard import start
from rubpy.bot.enums import ChatKeypadTypeEnum

load_dotenv()

app = BotClient(
    token=os.getenv("BOT_TOKEN"),
    rate_limit=float(os.getenv("RATE_LIMIT")),
    use_webhook=bool(os.getenv("USE_WEBHOOK"))
)

ADD_OWNER_PATTERN = re.compile(r"^افزودن مالک\s+([A-Za-z0-9_]+)$")
ADD_ADMIN_PATTERN = re.compile(r"^افزودن ادمین\s+([A-Za-z0-9_]+)$")
REMOVE_OWNER_PATTERN = re.compile(r"^حذف مالک\s+(@?[A-Za-z0-9_]+)$")
REMOVE_ADMIN_PATTERN = re.compile(r"^حذف ادمین\s+(@?[A-Za-z0-9_]+)$")

BOT_TEXT_RESPONSES = [
    "سلام! چی ازم میخوای؟ 😄",
    "هی رفیق! بگو ببینم چی شده؟ 🤔",
    "جونم؟ اینجام گوش میدم! 👂",
    "سلام سلام! سه‌سوته کمکت می‌کنم 😎",
    "الو! کی صدام زد؟ 😁",
    "قربونت، بگو ببینم چیکار میتونم انجام بدم برات؟ 😉",
    "ماموریت چیه رئیس؟ 💼",
    "چه خبر؟ آماده‌ام دست به کار بشم 💪"
]

async def get_random_question():
    database_path = "quiz.db"
    query = "SELECT question, options, answer FROM questions ORDER BY RANDOM() LIMIT 1;"
    async with aiosqlite.connect(database_path) as db:
        async with db.execute(query) as cursor:
            row = await cursor.fetchone()
            if row:
                question, options_json, answer = row
                options_data = json.loads(options_json)
                options = [option["title"] for option in options_data]
                correct_index: list = [
                    option["id"] if option["id"] == answer else 0
                    for option in options_data
                ].index(answer)
                return {
                    "question": question.strip(),
                    "options": options,
                    "correct_index": correct_index,
                }
            return None

async def fetch_user_by_identifier(session, identifier: str) -> models.User | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    username = None
    if identifier.startswith("@"):
        username = identifier[1:]
    if username:
        result = await session.execute(
            select(models.User).where(models.User.username == username)
        )
        user = result.scalar_one_or_none()
        if user:
            return user
    result = await session.execute(
        select(models.User).where(models.User.user_id == identifier)
    )
    user = result.scalar_one_or_none()
    if user:
        return user
    result = await session.execute(
        select(models.User).where(models.User.chat_id == identifier)
    )
    return result.scalar_one_or_none()

@app.on_start()
async def on_start(client: BotClient):
    await init_db()
    me = await client.get_me()
    print(me.username, "Bot started.")

@app.on_update(filters.private() & filters.button("pv_get_help"))
async def pv_get_help_handler(client: BotClient, update: Update):
    chat = await client.get_chat(update.chat_id)
    try:
        await update.reply(
            text=get_string("pv_start").format(chat.first_name),
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
    except Exception as exc:
        await client.send_message(
            chat_id=update.chat_id,
            text=get_string("pv_start").format(chat.first_name),
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
        print(f"pv_get_help_handler failed: {exc}")

@app.on_update(filters.private() & filters.button("my_groups"))
async def my_groups_handler(client: BotClient, update: Update):
    async with async_session() as session:
        result = await session.execute(
            select(models.Group)
            .join(models.Group.owner)
            .where(models.User.user_id == update.new_message.sender_id)
        )
        groups = result.scalars().all()
    if not groups:
        message = get_string("my_groups_empty")
    else:
        lines = [get_string("my_groups_header") + "\n"] + [f"{group.title or 'بدون نام'} ({group.chat_id})" for group in groups]
        message = "\n".join(lines)
    
    try:
        await update.reply(
            text=message,
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
    except Exception as exc:
        await client.send_message(
            chat_id=update.chat_id,
            text=message,
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
        print(f"my_groups_handler failed: {exc}")

@app.on_update(filters.private() & filters.commands("start"))
async def pv_start(client: BotClient, update: Update):
    async with async_session() as session:
        get_chat = await client.get_chat(update.chat_id)
        await crud.upsert_user(
            session,
            chat_id=update.chat_id,
            user_id=update.new_message.sender_id,
            username=get_chat.username,
        )
    try:
        await update.reply(
            text=get_string("pv_start").format(get_chat.first_name),
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
    except Exception as exc:
        await client.send_message(
            chat_id=update.chat_id,
            text=get_string("pv_start").format(get_chat.first_name),
            chat_keypad=start.get_keyboard(),
            chat_keypad_type=ChatKeypadTypeEnum.NEW)
        print(f"pv_start failed: {exc}")

@app.on_update(filters.group() & filters.text("نصب"))
async def install_handler(client: BotClient, update: Update):
    async with async_session() as session:
        result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        owner = result.scalar_one_or_none()

        if owner is None:
            return await update.reply(get_string("gp_install_failed"))

        get_chat = await client.get_chat(update.chat_id)
        group, status = await crud.upsert_group(
            session,
            group_id=update.chat_id,
            title=get_chat.title,
            owner=owner,
        )
        await crud.ensure_group_role(session, group.chat_id, owner.user_id, "owner")
        
        if status == "Exist":
            return

        await crud.log_install(session, group, owner)

    try:
        await update.reply(get_string("gp_install"))
    except Exception as exc:
        await client.send_message(chat_id=update.chat_id, text=get_string("gp_install"))
        print(f"install_handler failed: {exc}")

@app.on_update(filters.group() & filters.forward())
async def forward_handler(client: BotClient, update: Update):
    async with async_session() as session:
        result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = result.scalar_one_or_none()
        if group is None:
            return
        if not group.forward_lock:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        is_privileged = False
        if sender:
            if group.owner_id == sender.chat_id:
                is_privileged = True
            else:
                is_owner_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
                is_admin_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "admin")
                is_privileged = is_owner_role or is_admin_role
        if is_privileged:
            return
        await update.delete()

@app.on_update(filters.group() & filters.text(r"(?i)\b((?:https?://|www\.)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?:[/?#][^\s]*)?)", regex=True))
async def link_handler(client: BotClient, update: Update):
    async with async_session() as session:
        result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = result.scalar_one_or_none()
        if group is None:
            return
        if not group.link_lock:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        is_privileged = False
        if sender:
            if group.owner_id == sender.chat_id:
                is_privileged = True
            else:
                is_owner_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
                is_admin_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "admin")
                is_privileged = is_owner_role or is_admin_role
        if is_privileged:
            return
        await update.delete()

@app.on_update(filters.group() & filters.text(r"(?i)(?<!\w)@(?:[a-z0-9_]{3,32})(?!\w)", regex=True))
async def username_handler(client: BotClient, update: Update):
    async with async_session() as session:
        result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = result.scalar_one_or_none()
        if group is None:
            return
        if not group.username_lock:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        is_privileged = False
        if sender:
            if group.owner_id == sender.chat_id:
                is_privileged = True
            else:
                is_owner_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
                is_admin_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "admin")
                is_privileged = is_owner_role or is_admin_role
        if is_privileged:
            return
        await update.delete()

@app.on_update(filters.group() & filters.text("قفل لینک"))
async def lock_link_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("lock_link_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_link_not_allowed"))
        if group.link_lock:
            try:
                return await update.reply(get_string("lock_link_already_enabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_link_already_enabled"))
        await crud.update_group_locks(session, group.chat_id, link_lock=True)
        try:
            await update.reply(get_string("lock_link_enabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("lock_link_enabled"))
            print(f"lock_link_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("باز کردن لینک"))
async def unlock_link_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("unlock_link_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_link_not_allowed"))
        if not group.link_lock:
            try:
                return await update.reply(get_string("unlock_link_already_disabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_link_already_disabled"))
        await crud.update_group_locks(session, group.chat_id, link_lock=False)
        try:
            await update.reply(get_string("unlock_link_disabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("unlock_link_disabled"))
            print(f"unlock_link_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("قفل یوزرنیم"))
async def lock_username_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("lock_username_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_username_not_allowed"))
        if group.username_lock:
            try:
                return await update.reply(get_string("lock_username_already_enabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_username_already_enabled"))
        await crud.update_group_locks(session, group.chat_id, username_lock=True)
        try:
            await update.reply(get_string("lock_username_enabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("lock_username_enabled"))
            print(f"lock_username_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("باز کردن یوزرنیم"))
async def unlock_username_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("unlock_username_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_username_not_allowed"))
        if not group.username_lock:
            try:
                return await update.reply(get_string("unlock_username_already_disabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_username_already_disabled"))
        await crud.update_group_locks(session, group.chat_id, username_lock=False)
        try:
            await update.reply(get_string("unlock_username_disabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("unlock_username_disabled"))
            print(f"unlock_username_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("قفل فروارد"))
async def lock_forward_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("lock_forward_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_forward_not_allowed"))
        if group.forward_lock:
            try:
                return await update.reply(get_string("lock_forward_already_enabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("lock_forward_already_enabled"))
        await crud.update_group_locks(session, group.chat_id, forward_lock=True)
        try:
            await update.reply(get_string("lock_forward_enabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("lock_forward_enabled"))
            print(f"lock_forward_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("باز کردن فروارد"))
async def unlock_forward_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("unlock_forward_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_forward_not_allowed"))
        if not group.forward_lock:
            try:
                return await update.reply(get_string("unlock_forward_already_disabled"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("unlock_forward_already_disabled"))
        await crud.update_group_locks(session, group.chat_id, forward_lock=False)
        try:
            await update.reply(get_string("unlock_forward_disabled"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("unlock_forward_disabled"))
            print(f"unlock_forward_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("وضعیت"))
async def status_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        allowed = False
        if group.owner_id == sender.chat_id:
            allowed = True
        else:
            is_owner_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
            is_admin_role = await crud.user_has_role(session, group.chat_id, sender.user_id, "admin")
            allowed = is_owner_role or is_admin_role
        if not allowed:
            try:
                return await update.reply(get_string("status_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("status_not_allowed"))
        owner_main = None
        if group.owner_id:
            owner_query = await session.execute(
                select(models.User).where(models.User.chat_id == group.owner_id)
            )
            owner_main = owner_query.scalar_one_or_none()
        roles_result = await session.execute(select(models.GroupRole).where(models.GroupRole.group_id == group.chat_id))
        roles = roles_result.scalars().all()
        owner_ids = [role.user_id for role in roles if role.role == "owner"]
        admin_ids = [role.user_id for role in roles if role.role == "admin"]
        lookup_ids = list({*owner_ids, *admin_ids})
        users_map: dict[str, models.User] = {}
        if lookup_ids:
            users_result = await session.execute(select(models.User).where(models.User.user_id.in_(lookup_ids)))
            users = users_result.scalars().all()
            users_map = {user.user_id: user for user in users}

        unknown_text = get_string("status_unknown_user")

        def format_user(user: models.User | None, fallback: str) -> str:
            if user is None:
                return fallback
            if user.username:
                return f"@{user.username}"
            if user.user_id:
                return user.user_id
            return user.chat_id

        main_owner_id = owner_main.user_id if owner_main else None
        additional_owner_ids = [user_id for user_id in owner_ids if user_id != main_owner_id]
        additional_owner_ids = list(dict.fromkeys(additional_owner_ids))
        admin_ids = list(dict.fromkeys(admin_ids))
        additional_owners = [format_user(users_map.get(user_id), user_id) for user_id in additional_owner_ids]
        admins = [format_user(users_map.get(user_id), user_id) for user_id in admin_ids]
        main_owner_text = format_user(owner_main, unknown_text)
        if owner_main is None:
            main_owner_text = unknown_text
        additional_owner_text = ", ".join(additional_owners) if additional_owners else get_string("status_none")
        admin_text = ", ".join(admins) if admins else get_string("status_none")
        link_status = get_string("status_active") if group.link_lock else get_string("status_inactive")
        username_status = get_string("status_active") if group.username_lock else get_string("status_inactive")
        forward_status = get_string("status_active") if group.forward_lock else get_string("status_inactive")
        message = get_string("status_message").format(
            link_lock=link_status,
            username_lock=username_status,
            forward_lock=forward_status,
            main_owner=main_owner_text,
            additional_owners=additional_owner_text,
            admins=admin_text,
        )
        try:
            await update.reply(message)
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=message)
            print(f"status_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("شناسه من"))
async def get_me(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group:
            try:
                await update.reply(str(update.new_message.sender_id))
            except Exception as exc:
                await client.send_message(chat_id=update.chat_id, text=str(update.new_message.sender_id))
                print(f"get_me_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("راهنما"))
async def help_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group:
            try:
                await update.reply(get_string("help_message"))
            except Exception as exc:
                await client.send_message(chat_id=update.chat_id, text=get_string("help_message"))
                print(f"help_handler failed: {exc}")

@app.on_update(filters.group() & filters.text(r"^افزودن مالک\s+[A-Za-z0-9_]+$", regex=True))
async def add_owner_handler(client: BotClient, update: Update):
    text = (update.new_message.text or "").strip()
    match = ADD_OWNER_PATTERN.match(text)
    if match is None:
        return
    target_user_id = match.group(1)
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("add_owner_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("add_owner_not_allowed"))
        target_result = await session.execute(select(models.User).where(models.User.user_id == target_user_id))
        target = target_result.scalar_one_or_none()
        if target is None:
            try:
                return await update.reply(get_string("user_must_start_bot"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("user_must_start_bot"))
        already_owner = await crud.user_has_role(session, group.chat_id, target.user_id, "owner")
        if already_owner:
            try:
                return await update.reply(get_string("already_owner"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("already_owner"))
        await crud.ensure_group_role(session, group.chat_id, target.user_id, "owner")
        try:
            await update.reply(get_string("owner_added"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("owner_added"))
            print(f"add_owner_handler failed: {exc}")

@app.on_update(filters.group() & filters.text(r"^افزودن ادمین\s+[A-Za-z0-9_]+$", regex=True))
async def add_admin_handler(client: BotClient, update: Update):
    text = (update.new_message.text or "").strip()
    match = ADD_ADMIN_PATTERN.match(text)
    if match is None:
        return
    target_user_id = match.group(1)
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("add_admin_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("add_admin_not_allowed"))
        target_result = await session.execute(select(models.User).where(models.User.user_id == target_user_id))
        target = target_result.scalar_one_or_none()
        if target is None:
            try:
                return await update.reply(get_string("user_must_start_bot"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("user_must_start_bot"))
        already_admin = await crud.user_has_role(session, group.chat_id, target.user_id, "admin")
        if already_admin:
            try:
                return await update.reply(get_string("already_admin"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("already_admin"))
        await crud.ensure_group_role(session, group.chat_id, target.user_id, "admin")
        try:
            await update.reply(get_string("admin_added"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("admin_added"))
            print(f"add_admin_handler failed: {exc}")

@app.on_update(filters.group() & filters.text(r"^حذف ادمین\s+[@A-Za-z0-9_]+$", regex=True))
async def remove_admin_handler(client: BotClient, update: Update):
    text = (update.new_message.text or "").strip()
    match = REMOVE_ADMIN_PATTERN.match(text)
    if match is None:
        return
    target_identifier = match.group(1)
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("remove_admin_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("remove_admin_not_allowed"))
        target = await fetch_user_by_identifier(session, target_identifier)
        if target is None:
            try:
                return await update.reply(get_string("user_must_start_bot"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("user_must_start_bot"))
        already_admin = await crud.user_has_role(session, group.chat_id, target.user_id, "admin")
        if not already_admin:
            try:
                return await update.reply(get_string("admin_not_registered"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("admin_not_registered"))
        removed = await crud.remove_group_role(session, group.chat_id, target.user_id, "admin")
        if not removed:
            try:
                return await update.reply(get_string("remove_admin_error"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("remove_admin_error"))
        try:
            await update.reply(get_string("admin_removed"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("admin_removed"))
            print(f"remove_admin_handler failed: {exc}")

@app.on_update(filters.group() & filters.text(r"^حذف مالک\s+[@A-Za-z0-9_]+$", regex=True))
async def remove_owner_handler(client: BotClient, update: Update):
    text = (update.new_message.text or "").strip()
    match = REMOVE_OWNER_PATTERN.match(text)
    if match is None:
        return
    target_identifier = match.group(1)
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return
        sender_result = await session.execute(select(models.User).where(models.User.user_id == update.new_message.sender_id))
        sender = sender_result.scalar_one_or_none()
        if sender is None:
            return
        is_owner = False
        if group.owner_id == sender.chat_id:
            is_owner = True
        else:
            is_owner = await crud.user_has_role(session, group.chat_id, sender.user_id, "owner")
        if not is_owner:
            try:
                return await update.reply(get_string("remove_owner_not_allowed"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("remove_owner_not_allowed"))
        target = await fetch_user_by_identifier(session, target_identifier)
        if target is None:
            try:
                return await update.reply(get_string("user_must_start_bot"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("user_must_start_bot"))
        if group.owner_id == target.chat_id:
            try:
                return await update.reply(get_string("cannot_remove_primary_owner"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("cannot_remove_primary_owner"))
        already_owner = await crud.user_has_role(session, group.chat_id, target.user_id, "owner")
        if not already_owner:
            try:
                return await update.reply(get_string("owner_not_registered"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("owner_not_registered"))
        removed = await crud.remove_group_role(session, group.chat_id, target.user_id, "owner")
        if not removed:
            try:
                return await update.reply(get_string("remove_owner_error"))
            except Exception as exc:
                return await client.send_message(chat_id=update.chat_id, text=get_string("remove_owner_error"))
        try:
            await update.reply(get_string("owner_removed"))
        except Exception as exc:
            await client.send_message(chat_id=update.chat_id, text=get_string("owner_removed"))
            print(f"remove_owner_handler failed: {exc}")

@app.on_update(filters.group() & filters.text(r"بات|ربات|نیون", regex=True))
async def bot_text_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group:
            try:
                await update.reply(random.choice(BOT_TEXT_RESPONSES))
            except Exception as exc:
                await client.send_message(chat_id=update.chat_id, text=random.choice(BOT_TEXT_RESPONSES))
                print(f"bot_text_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("جوک"))
async def bot_text_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://shython-apis.liara.run/joke/random") as response:
                    data = await response.json()
                    try:
                        await update.reply(data["text"])
                    except Exception as exc:
                        await client.send_message(chat_id=update.chat_id, text=data["text"])
                        print(f"joke_handler failed: {exc}")

@app.on_update(filters.group() & filters.text("چالش"))
async def challenge_handler(client: BotClient, update: Update):
    async with async_session() as session:
        group_result = await session.execute(select(models.Group).where(models.Group.chat_id == update.chat_id))
        group = group_result.scalar_one_or_none()
        if group:
            question = await get_random_question()
            if question:
                try:
                    await client._make_request(
                        "sendPoll", {
                            "chat_id": update.chat_id,
                            "question": question["question"],
                            "options": question["options"],
                            "reply_to_message_id": update.new_message.message_id,
                            "type": "Quiz",
                            "correct_option_index": question["correct_index"],
                            "is_anonymous": False,
                            "disable_notification": False,
                            }
                        )
                
                except Exception:
                    await client._make_request(
                    "sendPoll", {
                        "chat_id": update.chat_id,
                        "question": question["question"],
                        "options": question["options"],
                        "type": "Quiz",
                        "correct_option_index": question["correct_index"],
                        "is_anonymous": False,
                        "disable_notification": False,
                        }
                    )

@app.on_update(filters.private() & filters.commands("myid"))
async def myid_handler(client: BotClient, update: Update):
    try:
        await update.reply(f"ID شما:\n{update.chat_id}")
    except Exception:
        await client.send_message(chat_id=update.chat_id, text=f"ID شما:\n{update.chat_id}")

@app.on_update(filters.private() & filters.commands("broadcast"))
async def broadcast_handler(client: BotClient, update: Update):
    message_text = (update.new_message.text or "").strip()
    parts = message_text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        try:
            return await update.reply("لطفا پیام مورد نظر را بعد از دستور بنویسید.")
        except Exception:
            return await client.send_message(chat_id=update.chat_id, text="لطفا پیام مورد نظر را بعد از دستور بنویسید.")

    allowed_ids_env = os.getenv("BROADCAST_ALLOWED_IDS")
    if allowed_ids_env:
        allowed_ids = {item.strip() for item in allowed_ids_env.split(",") if item.strip()}
        if str(update.chat_id) not in allowed_ids:
            try:
                return await update.reply("شما مجاز به استفاده از این دستور نیستید.")
            except Exception:
                return await client.send_message(chat_id=update.chat_id, text="شما مجاز به استفاده از این دستور نیستید.")

    broadcast_text = parts[1].strip()

    async with async_session() as session:
        result = await session.execute(select(models.Group.chat_id))
        chat_ids = result.scalars().all()

    if not chat_ids:
        try:
            return await update.reply("هیچ گروهی برای ارسال پیام یافت نشد.")
        except Exception:
            return await client.send_message(chat_id=update.chat_id, text="هیچ گروهی برای ارسال پیام یافت نشد.")

    msg = None
    try:
        msg = await update.reply("در حال ارسال پیام...")
    except Exception:
        await client.send_message(chat_id=update.chat_id, text="در حال ارسال پیام...")

    sent_count = 0
    failed_count = 0

    for chat_id in chat_ids:
        try:
            await client.send_message(chat_id=chat_id, text=broadcast_text)
            sent_count += 1
        except Exception as exc:
            failed_count += 1
            print(f"Broadcast failed for {chat_id}: {exc}")
        
        try:
            if msg:
                await msg.edit_text(new_text=f"در حال ارسال پیام...\n\nارسال برای {sent_count} گروه انجام شد.\n\nارسال برای {failed_count} گروه ناموفق بود.")
        except Exception as exc:
            print(f"Failed to edit broadcast message: {exc}")

    try:
        if msg:
            await msg.edit_text(new_text=f"پیام برای {sent_count} گروه ارسال شد.\n\nارسال برای {failed_count} گروه ناموفق بود.")
        else:
            await client.send_message(chat_id=update.chat_id, text=f"پیام برای {sent_count} گروه ارسال شد.\n\nارسال برای {failed_count} گروه ناموفق بود.")
    except Exception as exc:
        print(f"Failed to edit broadcast message: {exc}")

if __name__ == "__main__":
    app.run(
        webhook_url=os.getenv("WEBHOOK_URL"),
        path=os.getenv("WEBHOOK_PATH"),
        port=int(os.getenv("WEBHOOK_PORT"))
    )