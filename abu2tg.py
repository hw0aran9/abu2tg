#from socket import SO_J1939_SEND_PRIO
#from urllib import response
import kafka
import requests
import json
import sqlite3
import time
import flag #для отправки emoji
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import urllib.parse

from config import SOURCE, TELEGRAM, DB, BOT, REGEX, REPLACEMENTS

conn = sqlite3.connect(DB['name'])
cur = conn.cursor()

null = []

def get_streams():
    cur.execute("select * from streams")
    return cur.fetchall()    

def get_full_thread(board, thread_id):
    response = requests.get(f"{SOURCE['url']}/{board}/res/{str(thread_id)}.json")
    result = json.loads(response.content.decode('utf-8'))['threads'][0]['posts']
    
    return result

def get_latest_posts(board, thread_id, after):
    response = requests.get(f"{SOURCE['url']}/api/mobile/v2/after/{board}/{thread_id}/{after}")
    result = json.loads(response.content.decode('utf-8'))['posts'][1:]
    # удаляем самый первый элемент списка, чтобы не было дублей
    # дубли постов будут, так как в базе запоминается последний обработанный 
    # пост, и если запрашивать метод API after по нему - он будет возвращен первым
    # поэтому первцй элемент нам более не нужен
    return result

def get_flag_emoji(text): 

    try:
        country_code = re.findall(REGEX['flag'], text)[0][2]
        result = str(flag.flag(country_code))
    except Exception as e:
        print('get_flag_emoji: '+str(e))
        result = '🟥'
    return result

def get_date_from_ts(ts):
    try:
        result = str(datetime.fromtimestamp(ts))
    except Exception as e:
        result = 'NO DATE'
        print(e)
    return result

def get_anon_id(html):
    try:
        result = f"<b>{str(re.findall(REGEX['anon'], str(html))[0][1])}</b>"
        result = result.replace('&nbsp;', ' ')
    except Exception as e:
        print('get_anon_id: '+str(e))
        result = '<i>Heaven</i>'
    return result

def get_converted_text(html):
    # TODO переписать, проитерировав все теги через find_all() без аргументов
    # добавить в конфиг правила обработки тегов
    soup = BeautifulSoup(html, 'html.parser')
    brs = soup.find_all('br')
    for tag in brs:
        tag.replace_with('\n')
    
    spans_unkfunc = soup.find_all('span', attrs={'class':'unkfunc'})
    for tag in spans_unkfunc:
        tag.name = "em"
        del tag.attrs

    spans_censors = soup.find_all('span', attrs={'style': re.compile(r"color")})
    for tag in spans_censors:
        tag.name = "b"
        del tag.attrs

    spans_u = soup.find_all('span', attrs={'class':'u'})
    for tag in spans_u:
        tag.name = "u"
        del tag.attrs
    
    spans_o = soup.find_all('span', attrs={'class':'o'})
    for tag in spans_o:
        tag.name = "em"
        del tag.attrs

    spoilers = soup.find_all('span', attrs={'class':'spoiler'})
    for tag in spoilers:
        tag['class'] = 'tg-spoiler'

    striked = soup.find_all('span', attrs={'class': 's'})
    for tag in striked:
        tag.name = "s"
        del tag.attrs
    
    bolds = soup.find_all('strong')
    for tag in bolds:
        tag.name = "b"
        del tag.attrs

    itals = soup.find_all('em')
    for tag in itals: 
        tag.name = "i"

    sups = soup.find_all('sup')
    for tag in sups:
        tag.name = 'span'
        tag['class'] = 'tg-spoiler'
    
    subs = soup.find_all('sub')
    for tag in subs:
        tag.name = 'span'
        tag['class'] = 'tg-spoiler'    

    links = soup.find_all('a')
    for tag in links:
        del tag['class']
        del tag['data-num']
        del tag['data-thread']
        tag['href'] = SOURCE['url']+tag['href']
    
    for k in REPLACEMENTS.keys():
        soup = str(soup).replace(k, REPLACEMENTS[k])
    
    soup = BeautifulSoup(soup, 'html.parser')
    
    if len(str(soup)) > TELEGRAM['txt_limit']:
        print(f"too long ({len(str(soup))} > {TELEGRAM['txt_limit']}) - removing tags")
        all_tags = soup.find_all()
        for tag in all_tags:
            tag.extract()

    if len(str(soup)) > TELEGRAM['txt_limit']:
        print(f"still too long ({len(str(soup))} > {TELEGRAM['txt_limit']}) reducing text length")
        soup = str(soup)[0:TELEGRAM['txt_limit']]+'[...]'
    
    result = str(soup)
    return result

def send_message(chat_id, text, parse_mode):
    response = requests.get(f"{TELEGRAM['url']}bot{BOT['token']}/sendMessage?chat_id={chat_id}&parse_mode={parse_mode}&text={text}")
    print(response.status_code)    
    if response.status_code == 200:
        message_id = response.json()['result']['message_id']
    else:
        message_id = 0
        print(text, '>>>>>', response.content)
    return message_id
    

    #return
    #TODO check image size before sending it to Telegram by URL - 
    #API restrictions are <=5Mb for image and 20Mb for other files sent by URL

def send_single_photo(chat_id, url):
    response = requests.get(f"{TELEGRAM['url']}bot{BOT['token']}/sendPhoto?chat_id={chat_id}&photo={url}")
    print(f"[{response.status_code}]: {url}")

POST_TEMPLATE = "🆔{num} {anon}{emoji}\n{date}\n\n{text}"

while True:
    streams = get_streams()
    for stream in streams:
        print(f"Stream #{stream[0]}: {str(stream[1])}/{str(stream[2])} > {str(stream[4])}. Last post: {str(stream[3])}")
        if not stream[3]:
            print(f"Getting full thread {str(stream[1])}/{str(stream[2])}...")
            posts = get_full_thread(stream[1], stream[2])
        else:
            print(f"Getting fresh posts after  {str(stream[3])}...")
            posts = get_latest_posts(stream[1], stream[2], stream[3])
   
        print(f"Executing task of {str(len(posts))} posts...")
        if posts == []:
            print(f'No new posts for Stream #{stream[0]}')
            break 
        for post in posts:
            print(f"Sending [{posts.index(post)+1}/{len(posts)}]")
            try:    
                msg_id = send_message(
                    stream[4], 
                        POST_TEMPLATE.format(
                        num = str(post['num']), 
                        anon = get_anon_id(post['name']) if 'name' in post.keys() else '<i>Аноним</i>', 
                        emoji = get_flag_emoji(post['icon']) if 'icon' in post.keys() else '🐽',
                        date = get_date_from_ts(post['timestamp']),
                        text = get_converted_text(post['comment'])
                        ),
                        'HTML'
                    )
                print(f"Post {str(post['num'])} sent. Telegram ID: {msg_id}")    
                cur.execute(f"update streams set src_last_post_id = {post['num']} where id = {stream[0]}")
                cur.execute("insert into mappings values (?,?,?)", (stream[0], post['num'], msg_id))
                conn.commit()
                print(f"Post {str(post['num'])} registered.")
            except Exception as e:
                print(f"Failed to send post {str(post['num'])}!", str(e))
            time.sleep(TELEGRAM['posting_delay'])
        print(f"Task {stream[0]} complete.")
    print('All tasks complete, restarting...')
    time.sleep(1)

    # только текст - send_message (chat_id, text)
    # только картинка - http_url (5Mb photo, 20Mb other) https://2ch.hk/po/src/46440864/16522706230210.jpg
    # только несколько картинок, но не более 10
    # только несколько картинок и видео, но не более 10
    # текст + 1 картинка
    # текст и несколько картинок/видео

# Post 48898973 sent. Telegram ID: 15067

# You can send 1 message per second to individual chats
# You can send 20 messages per minute to groups/channels
# But at that moment you cannot send more than 30 messages per second overall.