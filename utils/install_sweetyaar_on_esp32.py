#! /usr/bin/env python

import os
import pathlib
import tempfile

from absl import app
from absl import flags

FLAG_WIPE = flags.DEFINE_bool("wipe", True, "Whether to wipe flash memory")
FLAG_PORT = flags.DEFINE_string("port", "/dev/tty.usbserial-0001", "the /dev port to use")
FLAG_MICROPYTHON_BINARY_PATH = flags.DEFINE_string("micropython-binary", "~/MicroPython/images/esp32-20220618-v1.19.1.bin", "MicroPython image to use")

PROJECT_ROOT_FOLDER = pathlib.Path(__file__).parents[1]


def main(argv):
    print(f"Installing SweetYaar2.0 on {FLAG_PORT.value}")

    if FLAG_WIPE.value:
        wipe_flash(FLAG_PORT.value)
        flash_micropython(FLAG_PORT.value, FLAG_MICROPYTHON_BINARY_PATH.value)

    copy_python_code(FLAG_PORT.value)

    print("Done")


def wipe_flash(port):
    rc = os.system(f"esptool.py --chip esp32 --port {port} erase_flash")
    if rc != 0:
        raise RuntimeError("couldn't wipe flash memory")

def flash_micropython(port, binary_path):
    rc = os.system(f"esptool.py --chip esp32 --port {port} --baud 460800 write_flash -z 0x1000 {binary_path}")
    if rc != 0:
        raise RuntimeError("couldn't flash MicroPython")

def copy_python_code(port):
    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = pathlib.Path(tempdir)
        srcdir = tempdir / "src"
        libdir = tempdir / "lib"
        etcdir = tempdir / "etc"

        # Creating a local dir with all src files
        os.system(f"cp {PROJECT_ROOT_FOLDER}/*.py {tempdir}")
        os.system(f"mkdir {srcdir} && cp {PROJECT_ROOT_FOLDER}/src/*.py {srcdir}")
        os.system(f"mkdir {etcdir} && cp {PROJECT_ROOT_FOLDER}/etc/* {etcdir}")
        
        os.system(f"mkdir {libdir}")
        libs_to_install = ",".join(("chunk", "sdcard", "wave", "aioble"))
        os.system(f"cp -r {PROJECT_ROOT_FOLDER}/lib/{{{libs_to_install}}}* {libdir}")

        # Compile to mpy
        os.system(f"for i in $(find {tempdir}/lib -name '*.py'); do mpy-cross -march=xtensawin $i; done")
        os.system(f"find {tempdir}/lib -name '*.py' | xargs rm")
        # os.system(f"for i in $(find {tempdir}/src -name '*.py'); do mpy-cross -march=xtensawin $i; done")
        # os.system(f"find {tempdir}/src -name '*.py' | xargs rm")

        # Copy to board
        os.system(f"cd {PROJECT_ROOT_FOLDER} && rshell -p {port} 'rm -rf /pyboard/*; rsync {tempdir} /pyboard; ls -l /pyboard'")

if __name__ == "__main__":
    app.run(main)