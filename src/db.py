import sqlite3
import queue
import traceback
import threading

work_queue = queue.Queue()

def sqlite_worker():
    con = sqlite3.connect('data/logger.db', check_same_thread=False)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS telemetry(metric, value, message, timestamp)")
    cur.execute("CREATE TABLE IF NOT EXISTS monitor(name, value, timestamp)")
    while True:
        try:
            (sql, params), result_queue = work_queue.get()
            res = cur.execute(sql, params)
            con.commit()
            result_queue.put(res)
        except Exception as e:
            traceback.print_exc()

threading.Thread(target=sqlite_worker, daemon=True).start()

def db_write(sql, params=None):
    # you might not really need the results if you only use this
    # for writing unless you use something like https://www.sqlite.org/lang_returning.html
    result_queue = queue.Queue()
    work_queue.put(((sql, params), result_queue))
    return result_queue.get(timeout=5)

