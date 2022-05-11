
import time
import requests
import json
import sys
import threading
import argparse
import os

def get_json(url):
    url = url[:-4] + 'json'
    response = requests.get(url)
    return json.loads(response.text)

def download_file(url, path):
    # single file download
    site = 'https://2ch.hk'
    # site = 'https://2ch.pm'
    file = requests.get(site + url).content
    with open(path + url.split('/')[-1],'wb') as f:
        f.write(file)

def get_media(url):
    # prepare media data and print general media info

    j = get_json(url)
    media       = []
    videos      = 0
    total_size  = 0

    for post in j['threads'][0]['posts']:
        if post['files']:
            for file in post['files']:
                media.append(file['path'])
                total_size += file['size']

                if file['type'] in [6,10]: 
                    videos += 1
                
    print(f"Media: {len(media)}\tImages: {len(media) - videos}\t Videos: {videos}\nTotal size:\t{round(total_size / 1024, 2)} Mb")
    return(media, total_size)

def download_supervisor(got_media, thread, path, tdc):
    # multi threading downloading core

    thread = thread.split('/')[-1].split('.')[0]
    if not path:
        try:
            os.mkdir(thread)
        except FileExistsError:
            i = input("Folder {} exists. Redownload all?\n(It will delete folder's files) [Y/n] ".format(thread))
            if i.lower() in ['n','no','hell no']:
                sys.exit()
            [os.remove(os.path.join(thread, file)) for file in os.listdir(thread)]
            
        path = thread + "/"


    # print("Started at\t{}".format(time.strftime("%X")))
    iter = tdc
    thread = got_media[0][0:iter]
    tasks = []
    
    while got_media[0][iter:iter + tdc] != []:
        task = threading.Thread(target=lambda urls: [download_file(url, path) for url in urls], args=(got_media[0][iter:iter + tdc],))
        tasks.append(task)
        iter += tdc

    for i in tasks:
        i.start()   # start threads

    for i in tasks:
        i.join()    # wait for all threads to end

def main(thread, path, tdc):
    print('starting...')
    try:
        download_supervisor(get_media(thread), thread, path, tdc)
    except KeyboardInterrupt:
        print('Bye')
    except requests.exceptions.ConnectionError:
        print('Connection aborted')
    except json.decoder.JSONDecodeError:
        print('Seems like ghost thread')
    except requests.exceptions.MissingSchema:
        print("Wrong thread")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2ch_hk threads downloading tool")
    parser.add_argument("-t",   action="store", dest="thread",  help="Thread's number",             required=True)
    parser.add_argument("-p",   action="store", dest="path",    help="Path for downloaded stuff",   required=False)
    parser.add_argument("--tdc",action="store", dest="tdc",     help="Thread's division constant",  required=False,  default=15, type=int)
    args = parser.parse_args()

    main(args.thread, args.path, args.tdc)
    print('stop')