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
    # 1. middleware.py のパッチ
    middleware_path = "/app/backend/open_webui/utils/middleware.py"
    target_mid = """    if (
        'chat_id' in metadata
        and not metadata['chat_id'].startswith('local:')
        and not metadata['chat_id'].startswith('channel:')
    ):"""
    replacement_mid = """    if (
        metadata.get('chat_id')
        and not metadata['chat_id'].startswith('local:')
        and not metadata['chat_id'].startswith('channel:')
    ):"""
    
    # 2. main.py のパッチ
    main_path = "/app/backend/open_webui/main.py"
    target_main = """            if metadata.get('chat_id') and metadata.get('message_id'):
                # Update the chat message with the error
                try:
                    if not metadata['chat_id'].startswith('local:') and not metadata['chat_id'].startswith('channel:'):"""
    replacement_main = """            if metadata.get('chat_id') and metadata.get('message_id'):
                # Update the chat message with the error
                try:
                    chat_id = metadata.get('chat_id')
                    if chat_id and not chat_id.startswith('local:') and not chat_id.startswith('channel:'):"""

    res1 = patch_file(middleware_path, target_mid, replacement_mid)
    res2 = patch_file(main_path, target_main, replacement_main)
    
    if not res1 or not res2:
        sys.exit(1)

if __name__ == "__main__":
    main()
