# Sweet Yaar project

## Useful commands

### Check volume levels in an audio file

> ffmpeg -i $FILENAME -af volumedetect -f null /dev/null |& grep "volume:"

### Convert an audio file to WAV

> ffmpeg -i $INPUT_FILE -acodec pcm_s16le -ar 22050 $OUTPUT_FILE

### Automatically adjust volume

> ffmpeg -i $INPUT_FILE -af loudnorm=I=-16:LRA=11:TP=-1.5 -acodec pcm_s16le -ar 22050 $OUTPUT_FILE

## `sweetyaar.service` file

In order to start sweetyaar automatically on boot, the service file should be copied into `/etc/systemd/system` and then run `sudo systemctl daemon-reload; sudo systemctl enable sweetyaar.service`.

In order to start/stop sweetyaar manually: `sudo systemctl start myscript.service` and `sudo systemctl stop myscript.service`.

