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
    
    print("Before modification (rag.web.search):")
    rag_web_search = config_data.get("rag", {}).get("web", {}).get("search", {})
    print("  bypass_web_loader:", rag_web_search.get("bypass_web_loader"))
    print("  bypass_embedding_and_retrieval:", rag_web_search.get("bypass_embedding_and_retrieval"))
    
    # 誤って作成したルートの "web" キーを削除
    if "web" in config_data:
        print("Removing incorrect root 'web' key...")
        del config_data["web"]
        
    # 正しい階層の値を更新
    if "rag" not in config_data:
        config_data["rag"] = {}
    if "web" not in config_data["rag"]:
        config_data["rag"]["web"] = {}
    if "search" not in config_data["rag"]["web"]:
        config_data["rag"]["web"]["search"] = {}
        
    config_data["rag"]["web"]["search"]["bypass_web_loader"] = False
    config_data["rag"]["web"]["search"]["bypass_embedding_and_retrieval"] = False
    
    # DBに書き戻し
    new_config_str = json.dumps(config_data)
    c.execute("UPDATE config SET data=? WHERE id=1;", (new_config_str,))
    conn.commit()
    print("Successfully updated database config.")
    
    # 変更後の確認
    c.execute("SELECT data FROM config WHERE id=1;")
    row_new = c.fetchone()
    config_new = json.loads(row_new[0])
    rag_web_search_new = config_new.get("rag", {}).get("web", {}).get("search", {})
    print("After modification (rag.web.search):")
    print("  bypass_web_loader:", rag_web_search_new.get("bypass_web_loader"))
    print("  bypass_embedding_and_retrieval:", rag_web_search_new.get("bypass_embedding_and_retrieval"))
    print("  Root 'web' exists:", "web" in config_new)
    
    conn.close()

if __name__ == '__main__':
    main()
