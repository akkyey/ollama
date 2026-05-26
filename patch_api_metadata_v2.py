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
    middleware_path = "/app/backend/open_webui/utils/middleware.py"
    
    # 1. 3145行目付近のパッチ
    target_1 = """                        if not metadata.get('chat_id', '').startswith('local:') and not metadata.get(
                            'chat_id', ''
                        ).startswith('channel:'):"""
    replacement_1 = """                        if not (metadata.get('chat_id') or '').startswith('local:') and not (metadata.get(
                            'chat_id'
                        ) or '').startswith('channel:'):"""

    # 2. 3159行目付近のパッチ
    target_2 = """            if not metadata.get('chat_id', '').startswith('local:') and not metadata.get('chat_id', '').startswith(
                'channel:'
            ):  # Only update titles and tags for non-temp chats"""
    replacement_2 = """            if not (metadata.get('chat_id') or '').startswith('local:') and not (metadata.get('chat_id') or '').startswith(
                'channel:'
            ):  # Only update titles and tags for non-temp chats"""

    res1 = patch_file(middleware_path, target_1, replacement_1)
    res2 = patch_file(middleware_path, target_2, replacement_2)
    
    if not res1 or not res2:
        sys.exit(1)

if __name__ == "__main__":
    main()
