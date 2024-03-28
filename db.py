import sqlite3

def initialize_db(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS requests
                      (request_id TEXT PRIMARY KEY, response TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def insert_request_id(request_id, db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO requests (request_id, response, status) VALUES (?, ?, ?)", 
                   (request_id, None, 'pending'))
    conn.commit()
    conn.close()


def update_response(request_id, response, db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET response = ?, status = 'completed' WHERE request_id = ?", 
                   (response, request_id))
    conn.commit()
    conn.close()

def get_pending_request_ids(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT request_id FROM requests WHERE status = 'pending'")
    request_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return request_ids

def count_pending_requests(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM requests WHERE status = 'pending'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def count_completed_requests(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM requests WHERE status = 'completed'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_completed_requests(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT request_id, response FROM requests WHERE status = 'completed'")
    completed_requests = cursor.fetchall()
    conn.close()
    return completed_requests

def remove_request_id(request_id, db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM requests WHERE request_id = ?", (request_id,))
    conn.commit()
    conn.close()

def remove_requests_with_none_id(db_name="mech_requests.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM requests WHERE request_id IS NULL")
    conn.commit()
    conn.close()



