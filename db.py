import sqlite3
from pathlib import Path

DB_PATH = Path("securevote.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS eligible_voters (
        voter_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        is_registered INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS voters (
        voter_id TEXT PRIMARY KEY,
        face_embedding TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        FOREIGN KEY (voter_id) REFERENCES eligible_voters(voter_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voter_id TEXT NOT NULL,
        purpose TEXT NOT NULL,  -- register / vote
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS elections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        start_at TEXT NOT NULL,
        end_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY (election_id) REFERENCES elections(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER NOT NULL,
        voter_id TEXT NOT NULL,
        candidate_id INTEGER NOT NULL,
        voted_at TEXT NOT NULL,
        UNIQUE(election_id, voter_id),
        FOREIGN KEY (election_id) REFERENCES elections(id),
        FOREIGN KEY (voter_id) REFERENCES voters(voter_id),
        FOREIGN KEY (candidate_id) REFERENCES candidates(id)
    )
    """)

    conn.commit()
    conn.close()