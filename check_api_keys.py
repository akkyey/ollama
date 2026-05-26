import sqlite3

def main():
    conn = sqlite3.connect('/mnt/data/open-webui/webui.db')
    c = conn.cursor()
    c.execute("SELECT * FROM api_key;")
    keys = c.fetchall()
    print("API Keys:", keys)
    
    c.execute("SELECT id, email, role FROM user;")
    users = c.fetchall()
    print("Users:", users)

if __name__ == '__main__':
    main()
