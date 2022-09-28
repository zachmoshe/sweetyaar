#! /usr/bin/env python
import os
import pathlib 

from absl import app
from absl import flags
import boto3

FLAGS = flags.FLAGS
FLAG_BUCKET_NAME = flags.DEFINE_string("bucket-name", "sweetyaar.com", "AWS S3 bucket name to upload to.")
FLAG_WITH_IMAGES = flags.DEFINE_bool("with-images", False, "Whether to include images or not (just html+code)")

_WWW_FOLDER = "www"
_ENV_FILENAME = ".env"
_CONTENT_TYPES = {
    ".json": "text/json",
    ".html": "text/html", 
    ".js": "text/javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

def main(argv):
    s3 = boto3.client("s3")
    for f in pathlib.Path(_WWW_FOLDER).glob("**/*"):
        if not f.is_file() or f.name == ".DS_Store": 
            continue
        if not FLAG_WITH_IMAGES.value and "images" in (parent.name for parent in f.parents):
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