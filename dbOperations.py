import sqlite3
from datetime import datetime


DB_NAME = "conversationsID.db"

def init_db():

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT UNIQUE,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    


# Method to store the conversation ID and body into the database
def store_conversation(conversation_id, body):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO conversations (conversation_id, body, created_at)
            VALUES (?, ?, ?)
        ''', (conversation_id, body, datetime.now()))
        conn.commit()
    except Exception as e:
        print("[ERROR] Could not store conversation:", e)
    finally:
        conn.close()
        

# Method to retrieve the conversation body by conversation ID
def get_conversation_body(conversation_id):
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT body FROM conversations WHERE conversation_id = ?', (conversation_id,))
    row = c.fetchone()
    conn.close()
    if row:
        print(f"[DEBUG] Retrieved body length: {len(row[0])}")
    else:
        print("[DEBUG] No conversation found for given ID.")
    return row[0] if row else None

# Method to validate if a conversation ID exists in the database
def validate_conversation_id(conversation_id):

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT 1 FROM conversations WHERE conversation_id = ?', (conversation_id,))
    exists = c.fetchone() is not None
    conn.close()
    print(f"[DEBUG] Validation result for {conversation_id}: {'FOUND' if exists else 'NOT FOUND'}")
    return exists
