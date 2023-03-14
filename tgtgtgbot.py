import logging
import time
from telegram import Update  # https://github.com/python-telegram-bot/python-telegram-bot
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler
import json
import sqlite3
from sqlite3 import Error
from tgtg import TgtgClient, TgtgAPIError  # https://github.com/ahivert/tgtg-python
from requests.exceptions import ConnectionError

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='tgtgtgbot.log'
)


async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="/help   - this help\n"
                                        "/start  - start conversation (TODO)\n"
                                        "/pause  - pause subscription\n"
                                        "/resume - resume subscription\n"
                                        "/info   - show subscription info (TODO)\n"
                                        "/delete - delete my subscription(TODO)\n")


async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_chat.first_name
    user_is_bot = update.effective_user.is_bot
    if user_is_bot:
        # TODO: block bot-user
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Sorry, no bots allowed")
    else:
        # check status of this user and initiate registering
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=f"I'm a bot, please talk to me {user_first_name}!")


async def command_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # set pause flag in database for this user
    con = db_connection()
    cursor = con.cursor()
    cursor.execute("""UPDATE users SET pause=? WHERE userid_tg=?""", (1, update.effective_chat.id))
    con.commit()
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Your subscription has been paused.\n"
                                        "Reactivate your subscription with the command /resume")


async def command_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reset pause flag in database for this user
    con = db_connection()
    cursor = con.cursor()
    cursor.execute("""UPDATE users SET pause=? WHERE userid_tg=?""", (0, update.effective_chat.id))
    cursor.execute("""UPDATE users SET sent_deals=? WHERE userid_tg=?""", ('[]', update.effective_chat.id))
    con.commit()
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Your subscription has been resumed.\n"
                                        "Pause your subscription with the command /pause")


async def command_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show status for this user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="info")


async def command_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # remove this user from the database
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="delete")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Type /help for an overview of all commands")


def db_connection():
    conn = None
    try:
        conn = sqlite3.connect("tgtgtgbot.sqlite")
    except Error as e:
        print(e)
    return conn


def retrieve_active_user_list(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE pause=0")
    return cursor.fetchall()


def update_user(conn, telegram_user_id, message_sent_lst):
    cursor = conn.cursor()
    msl_json = json.dumps(message_sent_lst)
    cursor.execute("UPDATE users SET sent_deals = ? where userid_tg = ?", (msl_json, telegram_user_id))
    conn.commit()


async def job_tgtg(context: ContextTypes.DEFAULT_TYPE):
    dbconn = db_connection()
    active_user_list = retrieve_active_user_list(dbconn)
    logging.info(f"processing {len(active_user_list)} toogoodtogo user(s)")

    for user in active_user_list:
        update_user_flag = False
        sent_deals = [] if not user[7] else json.loads(user[7])

        tgtg_client = TgtgClient(access_token=user[1],
                                 refresh_token=user[2],
                                 user_id=user[3],
                                 cookie=user[4],)
        try:
            items = tgtg_client.get_items()
        except (TgtgAPIError, ConnectionError) as e:
            logging.error(e)
            time.sleep(10)
            continue

        for item in items:
            if item["items_available"] and item["in_sales_window"]:
                if item["item"]["item_id"] not in sent_deals:
                    message = f"{item['store']['store_name']} " \
                              f"{item['store']['store_location']['address']['address_line']} " \
                              f"{item['item']['name']} " \
                              f"{item['items_available']}"
                    await context.bot.send_message(chat_id=user[0], text=message)
                    sent_deals.append(item["item"]["item_id"])
                    update_user_flag = True
            elif item["item"]["item_id"] in sent_deals:
                sent_deals.remove(item["item"]["item_id"])
                update_user_flag = True

        if update_user_flag:
            update_user(dbconn, user[0], sent_deals)

    dbconn.close()

if __name__ == '__main__':
    with open('telegram_bot_token.txt', 'r') as tbt_file:
        telegram_bot_token = json.load(tbt_file)

    application = ApplicationBuilder().token(telegram_bot_token["telegram_bot_token"]).build()
    job_queue = application.job_queue

    help_handler = CommandHandler('help', command_help)
    start_handler = CommandHandler('start', command_start)
    pause_handler = CommandHandler('pause', command_pause)
    resume_handler = CommandHandler('resume', command_resume)
    status_handler = CommandHandler('status', command_info)
    delete_handler = CommandHandler('delete', command_delete)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)

    application.add_handler(help_handler)
    application.add_handler(start_handler)
    application.add_handler(pause_handler)
    application.add_handler(resume_handler)
    application.add_handler(status_handler)
    application.add_handler(delete_handler)

    application.add_handler(echo_handler)

    job_tgtg = job_queue.run_repeating(job_tgtg, interval=300, first=10)
    application.run_polling()
