SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR
authbind --deep poetry run python src/main.py 

# On exit reboot the device to allow for catastrophic reboots if needed.
sudo shutdown -r now