import sqlite3

conn = sqlite3.connect('config.db')
cur = conn.cursor()

cur.execute("""
    create table if not exists streams(
    
    id int primary key,
    src_board text,
    src_thread_id int,
    src_last_post_id int,
    dst_channel_id int

);
""")
conn.commit()

tasks = [
    (1, 'po', 46440864, None, -1001779229444)
]

for task in tasks:
    cur.execute("insert into streams values(?,?,?,?,?);", task)
    conn.commit()