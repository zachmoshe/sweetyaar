import init 

from src import audio_library
from src import audio_player
from src import config
from src import controller
from src import interfaces 

cfg = config.get_config()

al = audio_library.AudioLibrary(cfg["audio_library"])
ap = audio_player.AudioPlayer(cfg["audio_player"], preallocated_buffer=init.AUDIO_PLAYER_FILE_BUFFER)

# Initialize controller and interfaces.
ctl = controller.SweetYaarController(cfg=cfg["controller"], audio_library=al, audio_player=ap)
gpio_iface = interfaces.GPIOInterface(cfg=cfg["interfaces"]["gpio"])
ctl.register_interface(gpio_iface)

if True:  # change later to a switch
    bt_iface = interfaces.BluetoothInterface(cfg=cfg["interfaces"]["bluetooth"])
    ctl.register_interface(bt_iface)
    ctl.register_controller_state_update_listener(bt_iface.handle_controller_state_change)

ctl.take_control()
