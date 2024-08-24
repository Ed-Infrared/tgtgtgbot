import logging
import logging.handlers
import time
import json
import sqlite3

from telegram import Update  # https://github.com/python-telegram-bot/python-telegram-bot
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler
from tgtg import TgtgClient  # https://github.com/ahivert/tgtg-python

from sqlite3 import Error
from tgtg import TgtgAPIError, TgtgPollingError, TgtgLoginError
from requests.exceptions import ConnectionError
from email_validator import validate_email, EmailNotValidError  # https://github.com/JoshData/python-email-validator

log_handler = logging.handlers.TimedRotatingFileHandler('tgtgtgbot.log', when='midnight')
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
formatter.converter = time.localtime
log_handler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)


async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='/help   - this help\n'
                                        '/start  - start conversation\n'
                                        '/email  - register too good to go email\n'
                                        '/pause  - pause subscription\n'
                                        '/resume - resume subscription\n'
                                        '/info   - show subscription info (TODO)\n'
                                        '/delete - delete my subscription\n')


async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_chat.first_name
    user_is_bot = update.effective_user.is_bot
    if user_is_bot:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text='Sorry, no bots allowed')
    else:
        # check status of this user and initiate registering
        userid_tg = update.effective_chat.id
        con = db_connection()
        cursor = con.cursor()
        cursor.execute(f"""SELECT * FROM users WHERE userid_tg={userid_tg}""")
        result = cursor.fetchall()
        if len(result) == 0:
            # create row in dbase
            cursor.execute(f"""INSERT INTO users (userid_tg, pause, sent_deals) VALUES ({userid_tg}, 0, '[]');""")
            con.commit()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f'Welcome {user_first_name},\n'
                     f'To access your Too Good To Go account please send us your email associated with Too Good To Go '
                     f'with the command: /email <your email>'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f'Welcome back {user_first_name}'
            )
        con.close()


async def command_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # set pause flag in database for this user
    con = db_connection()
    cursor = con.cursor()
    cursor.execute(f"""UPDATE users SET pause=1 WHERE userid_tg={update.effective_chat.id}""")
    con.commit()
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Your subscription has been paused.\n"
                                        "Reactivate your subscription with the command /resume")


async def command_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reset pause flag in database for this user
    con = db_connection()
    cursor = con.cursor()
    cursor.execute(f"""UPDATE users SET pause=0 WHERE userid_tg={update.effective_chat.id}""")
    cursor.execute(f"""UPDATE users SET sent_deals='[]' WHERE userid_tg={update.effective_chat.id}""")
    con.commit()
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Your subscription has been resumed.\n"
                                        "Pause your subscription with the command /pause")


async def command_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show info for this user
    con = db_connection()
    cursor = con.cursor()
    cursor.execute(f"""SELECT * FROM users WHERE userid_tg={update.effective_chat.id}""")
    user = cursor.fetchall()[0]
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=f"info: {user[0]}")


async def command_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # remove this user from the database
    con = db_connection()
    cursor = con.cursor()
    cursor.execute(f"""DELETE FROM users WHERE userid_tg={update.effective_chat.id}""")
    con.commit()
    con.close()
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='Your data is deleted.\n'
                                        'To subscribe again type /start')


async def command_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # register user with tgtg api
    user_tgtg_email = "".join(context.args)
    # validate email
    try:
        v = validate_email(user_tgtg_email)
        user_tgtg_email = v["email"]
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text='An email is sent to you.\n'
                                            'To confirm your registration please click on the link provided.\n'
                                            'IMPORTANT! Do not click on the link on the same device that has '
                                            'the Too Good To Go app')
        try:
            client = TgtgClient(email=user_tgtg_email)
            credentials = client.get_credentials()
            # store credentials
            con = db_connection()
            cursor = con.cursor()
            cursor.execute(f"""UPDATE users SET 
                               tgtg_accesstoken="{credentials['access_token']}",
                               tgtg_refreshtoken="{credentials['refresh_token']}",
                               tgtg_userid="{credentials['user_id']}",
                               tgtg_cookie="{credentials['cookie']}"
                               WHERE userid_tg={update.effective_chat.id};""")
            con.commit()
            con.close()
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='Your Too Good To Go access is registered with me\n'
                                                'When your favorite deals are available I wll sent you a message.')
        except TgtgPollingError as e:
            logging.info(str(e))
    except EmailNotValidError as e:
        logging.info(f'{e}: {user_tgtg_email}')
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=str(e) + '\nPlease try again')


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='Type /help for an overview of all commands')


def db_connection():
    conn = None
    try:
        conn = sqlite3.connect('tgtgtgbot.sqlite')
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users
            ([userid_tg] INTEGER,
             [tgtg_accesstoken] TEXT,
             [tgtg_refreshtoken] TEXT,
             [tgtg_userid] TEXT,
             [tgtg_cookie] TEXT,
             [pause] INTEGER,
             [last_seen] INTEGER,
             [sent_deals] TEXT)
        """)
        conn.commit()
    except Error as e:
        logging.error(e)
    return conn


def retrieve_active_user_list(conn):
    cursor = conn.cursor()
    cursor.execute("""SELECT * FROM users WHERE pause=0 AND tgtg_cookie IS NOT NULL;""")
    return cursor.fetchall()


def update_sent_deals(conn, telegram_user_id, message_sent_lst):
    cursor = conn.cursor()
    msl_json = json.dumps(message_sent_lst)
    cursor.execute(f"""UPDATE users SET sent_deals='{msl_json}' where userid_tg={telegram_user_id};""")
    conn.commit()


async def job_tgtg(context: ContextTypes.DEFAULT_TYPE):
    dbconn = db_connection()
    active_user_list = retrieve_active_user_list(dbconn)
    logging.info(f'processing {len(active_user_list)} toogoodtogo user(s)')

    for user in active_user_list:
        update_user_flag = False
        sent_deals = [] if not user[7] else json.loads(user[7])

        tgtg_client = TgtgClient(access_token=user[1],
                                 refresh_token=user[2],
                                 user_id=user[3],
                                 cookie=user[4],)
        try:
            items = tgtg_client.get_items()
        except (TgtgAPIError, ConnectionError, TgtgLoginError, TgtgPollingError) as e:
            logging.error(e)
            time.sleep(10)
            continue

        for item in items:
            if item['items_available'] and item['in_sales_window']:
                if item['item']['item_id'] not in sent_deals:
                    message = f'{item["store"]["store_name"]} ' \
                              f'{item["store"]["store_location"]["address"]["address_line"]} ' \
                              f'{item["item"]["name"]} ' \
                              f'{item["items_available"]}\n' \
                              f'https://share.toogoodtogo.com/item/{item["item"]["item_id"]}/'
                    await context.bot.send_message(chat_id=user[0], text=message)
                    sent_deals.append(item['item']['item_id'])
                    update_user_flag = True
            elif item['item']['item_id'] in sent_deals:
                sent_deals.remove(item['item']['item_id'])
                update_user_flag = True

        if update_user_flag:
            update_sent_deals(dbconn, user[0], sent_deals)

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
    status_handler = CommandHandler('info', command_info)
    delete_handler = CommandHandler('delete', command_delete)
    email_handler = CommandHandler('email', command_email)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)

    application.add_handler(help_handler)
    application.add_handler(start_handler)
    application.add_handler(pause_handler)
    application.add_handler(resume_handler)
    application.add_handler(status_handler)
    application.add_handler(delete_handler)
    application.add_handler(email_handler)
    application.add_handler(echo_handler)

    job_tgtg = job_queue.run_repeating(job_tgtg, interval=300, first=10)
#    application.run_polling()

    application.run_webhook(
        listen='0.0.0.0',
        port=eval(telegram_bot_token["telegram_webhook_port"]),
        secret_token=telegram_bot_token["telegram_secret_token"],
        webhook_url=telegram_bot_token["telegram_webhook_url"] + ':' + telegram_bot_token["telegram_webhook_port"]
        )
