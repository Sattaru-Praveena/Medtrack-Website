import sqlite3

# Connect to database (creates file if not exists)
conn = sqlite3.connect('users.db')

# Create table
conn.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
)
''')

print("Users table created successfully.")
conn.close()