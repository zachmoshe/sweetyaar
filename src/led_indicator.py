import uasyncio as asyncio
from machine import Pin, PWM


_DEFAULT_RGB_LEDS_V_DROP = (1.9, 2.6, 2.7)

_RGB_COLORS = {
    "white": (255, 255, 255), 
    "gray": (128, 128, 128), 
    "red": (255, 0, 0), 
    "yellow": (255, 255, 0), 
    "green": (0, 255, 0), 
    "aqua": (0, 255, 255), 
    "blue": (0, 0, 255), 
    "purple": (255, 0, 255), 
}

_U16 = 2 ** 16 - 1

class LedIndicator():
    def __init__(self, red_gpio, green_gpio, blue_gpio, ):
        self.rgb_pins = [PWM(Pin(gpio)) for gpio in (red_gpio, green_gpio, blue_gpio)]
        for pwm in self.rgb_pins:
            pwm.freq(100)
        self._current_task = None
        self.off()
    
    def _change_color_rgb(self, r_255, g_255, b_255):
        u16_values = [int(v * _U16 / 255) for v in (r_255, g_255, b_255)]
        for pwm, u16_v in zip(self.rgb_pins, u16_values):
            pwm.duty_u16(u16_v)

    def set_color(self, color_name, intensity=1.0):
        if color_name not in _RGB_COLORS:
            raise ValueError(f"Unknown color '{color_name}'.")
        r_255, g_255, b_255 = _RGB_COLORS[color_name]
        r_255, g_255, b_255 = [int(val * intensity) for val in (r_255, g_255, b_255)]
        self._change_color_rgb(r_255, g_255, b_255)
    
    def off(self):
        self._change_color_rgb(0, 0, 0)

    async def blink(self, color, cycle_ms=200, intensity=1., times=None):
        ctr = 0
        while True:
            if times is not None and ctr >= times:
                break
            self.set_color(color, intensity)
            await asyncio.sleep_ms(cycle_ms // 2)
            self.off()
            if times is None or ctr != times - 1:  # No need to wait at the last cycle
                await asyncio.sleep_ms(cycle_ms // 2)
            ctr += 1
  
    def blink_sync(self, color, cycle_ms=200, intensity=1., times=None):
        self._current_task = asyncio.run(self.blink(color, cycle_ms, intensity, times))

    def stop_sync(self):
        if self._current_task is not None:
            self._current_task.cancel()
