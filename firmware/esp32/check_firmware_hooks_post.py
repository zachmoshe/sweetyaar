# PlatformIO post-link step: fails the build when a firmware hook's
# assumptions about the libraries no longer hold. See "Firmware hooks" in
# docs/engineering/firmware.md and tools/check_firmware_hooks.py.
import os
import subprocess

Import("env")  # noqa: F821  (provided by PlatformIO)


def check_firmware_hooks(source, target, env):
    platform = env.PioPlatform()
    root = os.path.abspath(os.path.join(env.subst("$PROJECT_DIR"), "..", ".."))
    command = [
        env.subst("$PYTHONEXE"), os.path.join(root, "tools", "check_firmware_hooks.py"),
        "--elf", str(target[0]),
        "--toolchain-bin", os.path.join(platform.get_package_dir("toolchain-xtensa-esp32"), "bin"),
        "--libbt", os.path.join(platform.get_package_dir("framework-arduinoespressif32"),
                                "tools", "sdk", "esp32", "lib", "libbt.a"),
    ]
    if subprocess.call(command) != 0:
        env.Exit(1)


env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", check_firmware_hooks)  # noqa: F821
