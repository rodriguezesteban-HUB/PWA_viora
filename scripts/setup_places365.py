#!/usr/bin/env python3
import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "data", "models", "places365")

FILES = {
    "resnet18_places365.pth.tar": "http://places2.csail.mit.edu/models_places365/resnet18_places365.pth.tar",
    "categories_places365.txt": "https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt",
}


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"ok: {dest}")
        return
    print(f"downloading: {url}")
    tmp = dest + ".tmp"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    print(f"saved: {dest}")


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for filename, url in FILES.items():
        download(url, os.path.join(MODEL_DIR, filename))


if __name__ == "__main__":
    main()
