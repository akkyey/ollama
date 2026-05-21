import urllib.request

print("=== Testing Internet Connectivity to HuggingFace ===")
try:
    req = urllib.request.Request(
        "https://huggingface.co/",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response = urllib.request.urlopen(req, timeout=10)
    print("HuggingFace connection: OK, Status Code:", response.getcode())
except Exception as e:
    print("HuggingFace connection: FAILED,", e)
