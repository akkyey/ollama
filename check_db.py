import sqlite3

def main():
    conn = sqlite3.connect('/mnt/data/open-webui/webui.db')
    c = conn.cursor()
    c.execute("PRAGMA table_info(config);")
    columns = c.fetchall()
    print("Columns of config:", columns)

if __name__ == '__main__':
    main()
