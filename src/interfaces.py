from machine import Pin
import time 
import uasyncio as asyncio

from src import controller


class GPIOInterface():
    def __init__(self, cfg): 
        animals_button_gpio = cfg["GPIO_animals_button"]
        songs_button_gpio = cfg["GPIO_songs_button"]
        self.button_debounce_ms = 500
        self.animals_btn = Pin(animals_button_gpio, Pin.IN, Pin.PULL_UP)
        self.songs_btn = Pin(songs_button_gpio, Pin.IN, Pin.PULL_UP)

    async def listen(self, actions_callback):
        btns = [self.animals_btn, self.songs_btn]

        last_trigger_time = time.ticks_ms()

        while True:
            if time.ticks_ms() - last_trigger_time < self.button_debounce_ms:
                continue  # too close to the last change

            if any(btn.value() == 0 for btn in btns): 
                self.buttons_pressed(actions_callback)
                last_trigger_time = time.ticks_ms()
            await asyncio.sleep_ms(100)


    def buttons_pressed(self, actions_callback):
        # At least one of the buttons were pressed.
        # Decide the state and send the right action to the handler
        animals_pressed = self.animals_btn.value() == 0  # pins are PULL_UP
        songs_pressed = self.songs_btn.value() == 0
        if animals_pressed and songs_pressed:
            actions_callback(controller.STOP_PLAYING)
        elif animals_pressed:
            actions_callback(controller.PLAY_ANIMAL_SOUND)
        elif songs_pressed:
            actions_callback(controller.PLAY_SONG)
        else:
            print("weird, but no button was pressed when got here...")