import sqlite3
import json

def main():
    conn = sqlite3.connect('/mnt/data/open-webui/webui.db')
    c = conn.cursor()
    c.execute('SELECT id, title, chat FROM chat ORDER BY updated_at DESC LIMIT 1;')
    row = c.fetchone()
    if row:
        chat_id, title, chat_str = row
        print(f"==================================================")
        print(f"CHAT ID: {chat_id} | TITLE: {title}")
        print(f"==================================================")
        chat_data = json.loads(chat_str)
        messages = chat_data.get('history', {}).get('messages', {})
        msg_list = sorted(messages.values(), key=lambda x: x.get('timestamp', 0))
        if msg_list:
            # 最後のメッセージを表示する
            msg = msg_list[-1]
            role = msg.get('role')
            content = msg.get('content')
            print(f"\n[LAST MESSAGE: {role.upper()}]")
            print(content)
            
            if 'sources' in msg:
                print('--- SOURCES ---')
                print(json.dumps(msg['sources'], indent=2, ensure_ascii=False))
            if 'statusHistory' in msg:
                print('--- STATUS HISTORY ---')
                print(json.dumps(msg['statusHistory'], indent=2, ensure_ascii=False))
            
            # その1つ前のユーザーメッセージも表示する
            if len(msg_list) > 1:
                prev_msg = msg_list[-2]
                print(f"\n[PREVIOUS MESSAGE: {prev_msg.get('role').upper()}]")
                print(prev_msg.get('content'))
                if 'statusHistory' in prev_msg:
                    print('--- PREVIOUS STATUS HISTORY ---')
                    print(json.dumps(prev_msg['statusHistory'], indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
