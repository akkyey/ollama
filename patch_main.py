import sys

def patch():
    file_path = "/app/backend/open_webui/main.py"
    with open(file_path, "r") as f:
        content = f.read()

    target = """                'function_calling': (
                    'native'
                    if (
                        form_data.get('params', {}).get('function_calling') == 'native'
                        or model_info_params.get('function_calling') == 'native'
                    )
                    else 'default'
                ),"""

    replacement = """                'function_calling': (
                    'native'
                    if (
                        (form_data.get('params', {}).get('function_calling') == 'native'
                        or model_info_params.get('function_calling') == 'native')
                        and model_id != 'gemma2:2b'
                    )
                    else 'default'
                ),"""

    if target in content:
        new_content = content.replace(target, replacement)
        with open(file_path, "w") as f:
            f.write(new_content)
        print("SUCCESS")
    else:
        # すでにパッチ適用済みか、ターゲットが見つからない場合
        if replacement in content:
            print("ALREADY PATCHED")
        else:
            print("ERROR: Target string not found in main.py")
            sys.exit(1)

if __name__ == "__main__":
    patch()
