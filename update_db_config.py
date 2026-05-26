import sqlite3
import json
import os

def main():
    db_path = '/app/backend/data/webui.db' if os.path.exists('/app/backend/data/webui.db') else '/mnt/data/open-webui/webui.db'
    print(f"Using database path: {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 現在の設定を取得
    c.execute("SELECT data FROM config WHERE id=1;")
    row = c.fetchone()
    if not row:
        print("Error: config table row with id=1 not found.")
        return
        
    config_str = row[0]
    config_data = json.loads(config_str)
    
    # 変更前の値を出力
    web_search = config_data.get("web", {}).get("search", {})
    print("Before modification:")
    print("  bypass_web_loader:", web_search.get("bypass_web_loader"))
    print("  bypass_embedding_and_retrieval:", web_search.get("bypass_embedding_and_retrieval"))
    
    # 値の更新
    if "web" not in config_data:
        config_data["web"] = {}
    if "search" not in config_data["web"]:
        config_data["web"]["search"] = {}
        
    config_data["web"]["search"]["bypass_web_loader"] = False
    config_data["web"]["search"]["bypass_embedding_and_retrieval"] = False
    
    # DBに書き戻し
    new_config_str = json.dumps(config_data)
    c.execute("UPDATE config SET data=? WHERE id=1;", (new_config_str,))
    conn.commit()
    print("Successfully updated database config.")
    
    # 変更後の確認
    c.execute("SELECT data FROM config WHERE id=1;")
    row_new = c.fetchone()
    config_new = json.loads(row_new[0])
    web_search_new = config_new.get("web", {}).get("search", {})
    print("After modification:")
    print("  bypass_web_loader:", web_search_new.get("bypass_web_loader"))
    print("  bypass_embedding_and_retrieval:", web_search_new.get("bypass_embedding_and_retrieval"))
    
    conn.close()

if __name__ == '__main__':
    main()
