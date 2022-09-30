import bluetooth
from machine import Pin, RTC
import struct
import time 
import uasyncio as asyncio

from lib import aioble
from src import bt_logger
from src import controller

logger = bt_logger.get_logger(__name__)


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
            actions_callback(controller.Actions.STOP_PLAYING)
        elif animals_pressed:
            actions_callback(controller.Actions.PLAY_ANIMAL_SOUND)
        elif songs_pressed:
            actions_callback(controller.Actions.PLAY_SONG)
        else:
            logger.warn("weird, but no button was pressed when got here...")


class BluetoothInterface:
    _ADV_APPEARANCE = 0x0280

    _UUID_BATTERY_SERVICE = bluetooth.UUID(0x180F)
    _UUID_CHAR_BATTERY_LEVEL = bluetooth.UUID(0x2A19)

    _UUID_SWEETYAAR_SERVICE = bluetooth.UUID("10000000-2504-2021-0000-000079616172")
    _UUID_CHAR_SWEETYAAR_CONTROL = bluetooth.UUID("10000001-2504-2021-0000-000079616172")
    _UUID_CHAR_CURRENTLY_PLAYING = bluetooth.UUID("10000002-2504-2021-0000-000079616172")
    _UUID_CHAR_INACTIVE_COUNTER_SEC = bluetooth.UUID("10000003-2504-2021-0000-000079616172")
    _UUID_CHAR_DAYTIME_MODE = bluetooth.UUID("10000004-2504-2021-0000-000079616172")
    _UUID_CHAR_LOG_MESSAGES = bluetooth.UUID("10000005-2504-2021-0000-000079616172")
    _UUID_CHAR_VOLUME = bluetooth.UUID("10000006-2504-2021-0000-000079616172")

    _UUID_CURRENT_TIME_SERVICE = bluetooth.UUID(0x1805)
    _UUID_CHAR_DATE_TIME = bluetooth.UUID(0x2A08)

    def __init__(self, cfg):
        self.name = cfg["device_name"]
        self.bt_addr_mode = 0x00 if cfg["mac_address_mode"] == "internal" else 0x01  # "internal" / "random"
        self.battery_service = aioble.Service(self._UUID_BATTERY_SERVICE)
        self.battery_level_char = aioble.Characteristic(self.battery_service, self._UUID_CHAR_BATTERY_LEVEL, notify=True, read=True)

        self.sweetyaar_service = aioble.Service(self._UUID_SWEETYAAR_SERVICE)
        self.sweetyaar_control_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_SWEETYAAR_CONTROL, notify=True, write=True)
        self.currently_playing_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_CURRENTLY_PLAYING, notify=True, read=True)
        self.inactive_counter_sec_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_INACTIVE_COUNTER_SEC, notify=True, read=True)
        self.daytime_mode_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_DAYTIME_MODE, notify=True, read=True)
        self.log_messages_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_LOG_MESSAGES, notify=True, read=True)        
        self.volume_char = aioble.Characteristic(self.sweetyaar_service, self._UUID_CHAR_VOLUME, notify=True, read=True)

        self.current_time_service = aioble.Service(self._UUID_CURRENT_TIME_SERVICE)
        self.date_time_char = aioble.Characteristic(self.current_time_service, self._UUID_CHAR_DATE_TIME, notify=True, read=True, write=True)

        aioble.register_services(
            self.battery_service, 
            self.sweetyaar_service, 
            self.current_time_service,
        )


    async def advertise(self, adv_uuid=_ADV_APPEARANCE):
        """Advertises and connects to only a single device at a time."""
        while True: 
            try:
                logger.info("Advertising. Waiting for a BT connection..")
                bluetooth.BLE().config(gap_name=self.name, addr_mode=self.bt_addr_mode)
                async with await aioble.advertise(
                        -1,
                        name=self.name,
                        services=[
                            self._UUID_BATTERY_SERVICE, self._UUID_SWEETYAAR_SERVICE, self._UUID_CURRENT_TIME_SERVICE],
                        appearance=adv_uuid,
                    ) as connection:
                    logger.info(f"BT Connection from {connection.device}")
                    logger.bt_logger.connect_to_bt_characteristic(self.log_messages_char)
                    await connection.disconnected(timeout_ms=None)
            
            except (asyncio.core.TimeoutError, asyncio.core.CancelledError) as e:
                logger.error(f"Got error while connected to BT device: {repr(e)}")

    def handle_controller_event(self, event):
        if "currently_playing" in event:
            self.currently_playing_char.write(event["currently_playing"].encode("utf8"), send_update=True)
        if "kill_switch_counter" in event:
            self.inactive_counter_sec_char.write(struct.pack("<H", event["kill_switch_counter"]), send_update=True)
        if "daytime_mode" in event:
            self.daytime_mode_char.write(event["daytime_mode"].encode("utf8"), send_update=True)
        if "volume" in event:
            self.volume_char.write(struct.pack("<B", event["volume"]), send_update=True)


    async def listen(self, actions_callback):
        advertising_task = asyncio.create_task(self.advertise())
        battery_service_task = asyncio.create_task(self._run_battery_service())
        current_time_service = asyncio.create_task(self._run_current_time_service(actions_callback))
        control_service = asyncio.create_task(self._run_control_service(actions_callback))

    async def _run_control_service(self, actions_callback):
        while True:
            await self.sweetyaar_control_char.written()
            command_value = int(self.sweetyaar_control_char.read()[0])
            actions_callback(command_value)

    async def _run_battery_service(self):
        import random  # temp thing
        while True:
            self.battery_level_char.write(bytes([random.randint(0, 100)]), send_update=True)
            await asyncio.sleep(10)

    async def _run_current_time_service(self, actions_callback):
        rtc = RTC()

        def _publish_device_time():
            """Publishes the board's time to the client."""
            local_year, local_month, local_day, _, local_hours, local_minutes, local_seconds, _ = rtc.datetime()
            value = struct.pack("<HBBBBB", local_year, local_month, local_day, local_hours, local_minutes, local_seconds)
            self.date_time_char.write(value, send_update=True)

        async def _constantly_publish_device_time():
            while True:
                _publish_device_time()
                await asyncio.sleep(60)  # publish every minute.

        async def _update_device_time():
            """Updates the board's time from the computer client."""
            while True:
                await self.date_time_char.written()
                datetime_value = self.date_time_char.read()
                local_year, local_month, local_day, local_hours, local_minutes, local_seconds = struct.unpack("<HBBBBB", datetime_value)
                rtc.datetime((local_year, local_month, local_day, None, local_hours, local_minutes, local_seconds, 0))
                _publish_device_time()
                actions_callback(controller.Actions.DEVICE_TIME_CHANGED)

        tasks = [asyncio.create_task(_constantly_publish_device_time()), asyncio.create_task(_update_device_time())]
        await asyncio.gather(*tasks)

