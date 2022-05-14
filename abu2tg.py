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

from config import SOURCE, TELEGRAM, DB, BOT, REGEX, REPLACEMENTS, MEDIA

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

def add_replies(post: dict, comment_field: str) -> dict:
    """
    Scans post text and adds
    list of replies (source ids)
    as a new key of post json
    """
    if not comment_field in post.keys():
        return post

    replies = []

    soup = BeautifulSoup(post[comment_field], 'html.parser')
    
    reply_links = soup.find_all('a', attrs={'class': 'post-reply-link'})
    for link in reply_links: 
        replies.append(link['data-num'])

    post['replies'] = replies
    return post

def remove_unsupported_media(post:dict) -> dict:
    if not 'files' in post.keys() or post['files'] == [] or post['files'] == None:
        return post

    files_list = post['files']
    files_list[:] = [x for x in files_list if x['type'] in MEDIA['supported_types']]
    #files_list[:] = [x for x in files_list if (x['width'] + x['height']) > MEDIA['pic_limit_size_hw']]
    return post
    
def get_mapped_value(stream, src_val: int) -> int:
    """
    Gets mapped value from database table.
    Table must contain both of the fields
    specified in args
    """
    cur.execute(f"select dst_id from mappings where stream_id = {stream} and src_id = {src_val} order by dst_id desc limit 1")
    try:
        result = cur.fetchall()[0][0]
    except Exception as e: 
        result = 0
        print(f"Failed to get mapped value for {src_val}: {str(e)}")
    return result

def get_converted_text(html, len_limit):
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

    reply_links = soup.find_all('a', attrs={'class': 'post-reply-link'})
    for link in reply_links:
        link.decompose()
    
    for k in REPLACEMENTS.keys():
        soup = str(soup).replace(k, REPLACEMENTS[k])
    
    soup = BeautifulSoup(soup, 'html.parser')
    
    if len(str(soup)) > len_limit:
        print(f"too long ({len(str(soup))} > {len_limit}) - removing tags")
        all_tags = soup.find_all()
        for tag in all_tags:
            tag.extract()

    if len(str(soup)) > len_limit:
        print(f"still too long ({len(str(soup))} > {len_limit}) reducing text length")
        soup = str(soup)[0:len_limit]+'[...]'
    
    result = str(soup)
    return result

def send_message(chat_id, text, reply_to, parse_mode):
    response = requests.get(f"{TELEGRAM['url']}bot{BOT['token']}/sendMessage?chat_id={chat_id}&parse_mode={parse_mode}&text={text}&reply_to_message_id={reply_to}&allow_sending_without_reply=True")
    print(response.status_code)    
    if response.status_code == 200:
        message_id = response.json()['result']['message_id']
    else:
        message_id = 0
        print(text, '>>>>>', response.content)
    return message_id
    

def send_media_group(chat_id: int, medias: list, caption, reply_to, parse_mode):
    
    media_list = []
    for media in medias:
        media_dict = {}
        media_dict['type'] = MEDIA['mapping'][media['type']] #как-то нечитаемо...
        media_dict['media'] = SOURCE['url']+media['path']
        media_list.append(media_dict)
        del media_dict
    media_list[0]['caption'] = caption
    media_list[0]['parse_mode'] = parse_mode
    
    print('sending')
    media_list = json.dumps(media_list)
    print(media_list)

    response = requests.get(f"{TELEGRAM['url']}bot{BOT['token']}/sendMediaGroup?chat_id={chat_id}&media={str(media_list)}&reply_to_message_id={reply_to}&allow_sending_without_reply=True")
    print(response.status_code)
    if response.status_code == 200:
        message_id = response.json()['result'][0]['message_id']
        #                                     ^^^
        # внимание, в структуре ответа получается так, что 
        # при отправке mediaGroup возвращается 
        # отдельный message_id на каждое медиа в группе
        # поэтому для будущих регистраций соответствий 
        # поста на 2ch и в телеге
        # для медиагруппы будем возвращать id первого поста в ней
    else:
        message_id = 0
        print('>>>>>', response.content)
    return message_id
    

#POST_TEMPLATE = "🆔{num} {anon}{emoji}\n{date}\n\n{text}"
POST_TEMPLATE = "🆔{num}\n{anon}{emoji}\n{date}\n{text}"

# send_media_group(-1001779229444, FILES, 'test caption', 23757, 'HTML')

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
   
        print(f"Executing task containing [{str(len(posts))}] posts...")
        if posts == []:
            print(f'No new posts for Stream #{stream[0]}')
            break 
        for post in posts:
            print(f"Sending post [{post['num']}] [{posts.index(post)+1}/{len(posts)}]")
            post = add_replies(post, 'comment')
            print(f"Checking if post is a reply to: {'>'+str(post['replies'][-1]) if post['replies'] != [] else str('')}")
                        
            post = remove_unsupported_media(post)

            if post['files'] is not None:
                try:    #блок кода для текстового поста
                    print('Sending media post...')
                    msg_id = send_media_group(
                        stream[4], 
                            post['files'],
                            POST_TEMPLATE.format(
                            num = str(post['num']), 
                            anon = get_anon_id(post['name']) if 'name' in post.keys() else '<i>Аноним</i>', 
                            emoji = get_flag_emoji(post['icon']) if 'icon' in post.keys() else '🐽',
                            date = get_date_from_ts(post['timestamp']),
                            text = get_converted_text(post['comment'], TELEGRAM['cap_limit'])
                            ),
                            get_mapped_value(stream[0], post['replies'][-1]) if post['replies'] != [] else 0,
                            'HTML'
                        )
                    print(f"Post {str(post['num'])} sent. Telegram ID: {msg_id}")    
                    cur.execute(f"update streams set src_last_post_id = {post['num']} where id = {stream[0]}")
                    cur.execute("insert into mappings values (?,?,?)", (stream[0], post['num'], msg_id))
                    conn.commit()
                    print(f"Post {str(post['num'])} registered.")
                except Exception as e:
                    print(f"Failed to send media post {str(post['num'])}!", str(e))
                time.sleep(TELEGRAM['posting_delay']*len(post['files'])) 
                # поскольку каждое медиа в группе считается отдельным сообщением
                # на эти сообщения распространяются лимиты на сранье
                # поэтому, отправив три картинки, мы ждем минимум 9 секунд!

            else:
                try:    #блок кода для текстового поста
                    print('Sending text post...')
                    msg_id = send_message(
                        stream[4], 
                            POST_TEMPLATE.format(
                            num = str(post['num']), 
                            anon = get_anon_id(post['name']) if 'name' in post.keys() else '<i>Аноним</i>', 
                            emoji = get_flag_emoji(post['icon']) if 'icon' in post.keys() else '🐽',
                            date = get_date_from_ts(post['timestamp']),
                            text = get_converted_text(post['comment'], TELEGRAM['txt_limit'])
                            ),
                            get_mapped_value(stream[0], post['replies'][-1]) if post['replies'] != [] else 0,
                            'HTML'
                        )
                    print(f"Post {str(post['num'])} sent. Telegram ID: {msg_id}")    
                    cur.execute(f"update streams set src_last_post_id = {post['num']} where id = {stream[0]}")
                    cur.execute("insert into mappings values (?,?,?)", (stream[0], post['num'], msg_id))
                    conn.commit()
                    print(f"Post {str(post['num'])} registered.")
                except Exception as e:
                    print(f"Failed to send text post {str(post['num'])}!", str(e))
                time.sleep(TELEGRAM['posting_delay'])
        print(f"Task {stream[0]} complete.")
    print('All tasks complete, restarting...')
    time.sleep(1)

