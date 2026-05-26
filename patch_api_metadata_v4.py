import sys

def patch_file(file_path, target, replacement):
    with open(file_path, "r") as f:
        content = f.read()
    
    if target in content:
        new_content = content.replace(target, replacement)
        with open(file_path, "w") as f:
            f.write(new_content)
        print(f"SUCCESS: Patched {file_path}")
        return True
    elif replacement in content:
        print(f"ALREADY PATCHED: {file_path}")
        return True
    else:
        print(f"WARNING: Target not found in {file_path}")
        return False

def main():
    socket_main_path = "/app/backend/open_webui/socket/main.py"
    
    # 1. 898行目のパッチ
    target_1 = """    # Channel mode: route pipeline output to channel message updates
    if request_info.get('chat_id', '').startswith('channel:'):"""
    replacement_1 = """    # Channel mode: route pipeline output to channel message updates
    if (request_info.get('chat_id') or '').startswith('channel:'):"""

    # 2. 920行目のパッチ
    target_2 = """        if update_db and message_id and not request_info.get('chat_id', '').startswith('local:'):"""
    replacement_2 = """        if update_db and message_id and not (request_info.get('chat_id') or '').startswith('local:'):"""

    res1 = patch_file(socket_main_path, target_1, replacement_1)
    res2 = patch_file(socket_main_path, target_2, replacement_2)
    
    if not res1 or not res2:
        sys.exit(1)

if __name__ == "__main__":
    main()
