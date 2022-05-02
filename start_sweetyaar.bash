SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR
authbind --deep poetry run python src/main.py 

# On exit reboot the device to allow for catastrophic reboots if needed.
# Only consider exits that the user asked for (by issuing the reboot command), otherwise
# every programatic error (missing module, ..) will cause a reboot loop.
if [ $? -eq 0 ]
then
   sudo shutdown -r now
fi
