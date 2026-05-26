import urllib.request
import json

url = "http://100.99.31.13:3000/api/v1/models"
req = urllib.request.Request(url)
req.add_header("Authorization", "Bearer sk-testapikey1234567890abcdef")
req.add_header("User-Agent", "Mozilla/5.0")
try:
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode('utf-8'))
        print("Models:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print("Error:", e)
