_AUDIO_PLAYER_FILE_BUFFER_SIZE = 2048
_AUDIO_PLAYER_FILE_BUFFER = bytearray(_AUDIO_PLAYER_FILE_BUFFER_SIZE)

from src import sweetyaar_device

device = sweetyaar_device.SweetYaarDevice(audio_player_file_buffer=_AUDIO_PLAYER_FILE_BUFFER)
device.init()