import requests
import sys

URL = "https://www.englandrugby.com/fixtures-and-results/search-results?team=9045&season=2025-2026"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

print(f"Testing connection to: {URL}")
print(f"Python version: {sys.version}")

try:
    response = requests.get(URL, headers=HEADERS, timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success! Connection established.")
        print(f"Content length: {len(response.content)} bytes")
    else:
        print("Failed with status code.")
except Exception as e:
    print(f"Connection failed: {e}")
    print("\nNOTE: If you are on a Free PythonAnywhere account, you can only access specific whitelisted sites.")
    print("If this fails, 'englandrugby.com' might not be on the whitelist.")
