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
    main_path = "/app/backend/open_webui/main.py"
    target_main = """            error_detail = e.detail if isinstance(e, HTTPException) else str(e)
            log.error('Error processing chat payload: %s', error_detail)"""
    replacement_main = """            error_detail = e.detail if isinstance(e, HTTPException) else str(e)
            log.error('Error processing chat payload: %s', error_detail, exc_info=True)"""

    res = patch_file(main_path, target_main, replacement_main)
    if not res:
        sys.exit(1)

if __name__ == "__main__":
    main()
