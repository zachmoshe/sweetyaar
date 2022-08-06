import uasyncio as asyncio
# from microdot_asyncio import Microdot, Response
# from machine import PWM, Pin, Signal

cfg = {'log_path': 'sweetyaar.log', 'log_level': 'DEBUG', 'kill_switch_inactive_time_secs': 300, 'default_starting_volume': 70, 'nighttime_cutoff': '18:00', 'daytime_songs': ['recordings/songs/daytime/*.wav'], 'nighttime_songs': ['recordings/songs/nighttime/*.wav'], 'animals': {'yaar_callings': ['recordings/yaar_callings/*.wav'], 'animals_sounds': ['recordings/animals/*.wav']}, 'audio': {'volume_step': 10}, 'interfaces': {'gpio': {'gpio_mode': 'BOARD', 'animal_button_gpio_channel': 16, 'songs_button_gpio_channel': 11, 'button_debounce_ms': 1000}, 'keyboard': {'actions_mapping': {'PLAY_RANDOM_ANIMAL_SOUND': 'a', 'PLAY_RANDOM_SONG': 's', 'VOLUME_UP': '+', 'VOLUME_DOWN': '-', 'STOP': 't', 'KILL_SWITCH': 'k', 'REBOOT': 'r'}}, 'web': {'host': '0.0.0.0', 'port': 80, 'yaar_photos': ['src/templates/static/yaar_photos/*'], 'actions_mapping': {'PLAY_RANDOM_ANIMAL_SOUND': 'random-animal-sound', 'PLAY_RANDOM_SONG': 'random-song', 'VOLUME_UP': 'volume-up', 'VOLUME_DOWN': 'volume-down', 'STOP': 'stop-playing', 'KILL_SWITCH': 'kill-switch', 'REBOOT': 'reboot', 'OVERRIDE_DAYTIME': 'override-daytime', 'OVERRIDE_NIGHTTIME': 'override-nighttime'}}}}

print("initializing controller...")
ctl = controller.SweetYaarController(cfg)
print("taking control")
ctl.take_control()



# _RUNNING_INDICATOR_LED = Signal(Pin(16, Pin.OUT), invert=True)
# _RUNNING_INDICATOR_LED.off()

# app = Microdot()

# _INDEX_HTML = open("www/index.html", "rt").read()

# @app.route('/')
# async def index(req):
#     return Response(body=_INDEX_HTML, headers={"Content-Type": "text/html"})

# async def main():
#     await app.start_server(debug=True)

# _RUNNING_INDICATOR_LED.on()
# asyncio.run(main())

