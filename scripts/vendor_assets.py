"""Download front-end vendor assets so the portal works on isolated networks."""
import os
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(BASE, "ui", "assets", "vendor")

os.makedirs(os.path.join(VENDOR, "fontawesome", "css"), exist_ok=True)
os.makedirs(os.path.join(VENDOR, "fontawesome", "webfonts"), exist_ok=True)

DOWNLOADS = [
    ("https://cdn.tailwindcss.com",
     os.path.join(VENDOR, "tailwindcss.js")),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
     os.path.join(VENDOR, "fontawesome", "css", "all.min.css")),
]

WF_BASE = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/"
WF_FILES = [
    "fa-brands-400.woff2", "fa-regular-400.woff2", "fa-solid-900.woff2",
    "fa-brands-400.woff", "fa-regular-400.woff", "fa-solid-900.woff",
    "fa-brands-400.ttf", "fa-regular-400.ttf", "fa-solid-900.ttf",
]
for name in WF_FILES:
    DOWNLOADS.append((WF_BASE + name, os.path.join(VENDOR, "fontawesome", "webfonts", name)))

for url, dest in DOWNLOADS:
    print(f"Downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(dest, "wb") as out_file:
        out_file.write(response.read())
    print(f"  OK ({os.path.getsize(dest)} bytes)")

print("All vendor assets downloaded.")
