import requests
import json
import sqlite3
import time
import flag #для отправки emoji

from telethon import TelegramClient
from config import ENDPOINT, TELEGRAM, APP, DB, BOT

client = TelegramClient('abu2tg', APP['api_id'], APP['api_hash'])
client.connect()

conn = sqlite3.connect(DB['name'])
cur = conn.cursor()

def get_streams():
    cur.execute("select * from streams")
    return cur.fetchall()    

def get_full_thread(board, thread_id):
    response = requests.get(f"{ENDPOINT['url']}{board}/res/{str(thread_id)}.json")
    result = json.loads(response.content.decode('utf-8'))['threads'][0]['posts']
    return result

def get_latest_posts(board, thread_id, after):
    response = requests.get(f"{ENDPOINT['url']}api/mobile/v2/after/{board}/{thread_id}/{after}")
    result = json.loads(response.content.decode('utf-8'))['posts']
    return result

    # только текст - send_message (chat_id, text)
    # только картинка - http_url (5Mb photo, 20Mb other) https://2ch.hk/po/src/46440864/16522706230210.jpg
    # только несколько картинок, но не более 10
    # только несколько картинок и видео, но не более 10
    # текст + 1 картинка
    # текст и несколько картинок/видео

# while True:
#     streams = get_streams()
#     for stream in streams:
#         print(f"Data stream #{stream[0]}: from {str(stream[1])}/, thread {str(stream[2])} to {str(stream[4])}. Last processed post was {str(stream[3])}")
#         if not stream[3]:
#             posts = get_full_thread(stream[1], stream[2])
#         else:
#             posts = get_latest_posts(stream[1], stream[2], stream[3])

#         cur.execute(f"update streams set src_last_post_id = {posts[-1]['num']} where id = {stream[0]}")
#         conn.commit()
        
#         print(f"Last post from thread {stream[2]} for now is {posts[-1]['num']}")
#         #print(json.dumps(posts[-1], indent=4, ensure_ascii=False))
#         #send_message(stream[4], f"Stream {stream[0]}: from {str(stream[1])}/, thread {str(stream[2])} to {str(stream[4])} channel. Last processed post {str(stream[3])}")
#         send_single_photo(stream[4], 'https://2ch.hk/po/src/46440864/16522705980270.mp4')
#         print('All tasks done')
#     time.sleep(30)

