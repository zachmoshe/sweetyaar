#! /usr/bin/env python
import os
import pathlib 

from absl import app
from absl import flags
import boto3

FLAGS = flags.FLAGS
FLAG_BUCKET_NAME = flags.DEFINE_string("bucket-name", "sweetyaar.com", "AWS S3 bucket name to upload to.")
FLAG_UPLOAD_ROOT_ONLY = flags.DEFINE_bool("upload-root-only", False, "Whether to upload root files only or all descendants.")

_WWW_FOLDER = "www"
_ENV_FILENAME = ".env"
_CONTENT_TYPES = {
    ".json": "text/json",
    ".html": "text/html", 
    ".js": "text/javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".css": "text/css",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
}

def main(argv):
    s3 = boto3.client("s3")
    root_path = pathlib.Path(_WWW_FOLDER)
    files = (root_path.glob("*") if FLAG_UPLOAD_ROOT_ONLY.value else root_path.glob("**/*"))
    for f in files:
        if not f.is_file() or f.name == ".DS_Store": 
            continue
        rel_name = f.relative_to(_WWW_FOLDER)
        print(f"Uploading {f} to s3://{FLAG_BUCKET_NAME.value}/{rel_name}")
        s3.upload_file(str(f), FLAG_BUCKET_NAME.value, str(rel_name), ExtraArgs={'ContentType': _CONTENT_TYPES.get(f.suffix, "text")})

def load_env():
    if not pathlib.Path(_ENV_FILENAME).exists():
        return

    with open(_ENV_FILENAME, "rt") as f:
        for line in f:
            name, value = line.strip().split("=")
            os.environ[name] = value

if __name__ == "__main__":
    load_env()
    app.run(main)