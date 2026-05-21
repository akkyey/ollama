import urllib.request
import sys

print("=== Starting HTTP Endpoint Verification ===")
# 1. Ollama APIの検証
try:
    response = urllib.request.urlopen("http://127.0.0.1:11434/")
    print("Ollama API connection: OK, Status Code:", response.getcode())
except Exception as e:
    print("Ollama API connection: FAILED,", e)

# 2. Open WebUI (Tailscale IP) の検証
try:
    req = urllib.request.Request(
        "http://100.99.31.13:3000/",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response = urllib.request.urlopen(req)
    print("Open WebUI (Tailscale IP) connection: OK, Status Code:", response.getcode())
except Exception as e:
    print("Open WebUI (Tailscale IP) connection: FAILED,", e)

# 3. Open WebUI (127.0.0.1:3000) の検証 (バインド制限により拒否されるべき)
try:
    req = urllib.request.Request(
        "http://127.0.0.1:3000/",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response = urllib.request.urlopen(req, timeout=5)
    print("Open WebUI (Localhost 127.0.0.1) connection: UNEXPECTEDLY OK, Status Code:", response.getcode())
except Exception as e:
    print("Open WebUI (Localhost 127.0.0.1) connection: EXPECTEDLY BLOCKED,", e)
