import uasyncio as asyncio
from machine import Pin, PWM
import neopixel

from micropython import const


_DEFAULT_RGB_LEDS_V_DROP = const((1.9, 2.6, 2.7))

_RGB_COLORS = const({
    "white": (255, 255, 255), 
    "gray": (128, 128, 128), 
    "red": (255, 0, 0), 
    "yellow": (255, 255, 0), 
    "green": (0, 255, 0), 
    "aqua": (0, 255, 255), 
    "blue": (0, 0, 255), 
    "purple": (255, 0, 255), 
})

_U16 = const(2 ** 16 - 1)


# A context manager for indicating that a process runs using the LED.
class LedIndicate:
    def __init__(self, led, color):
        self.led = led
        self.color = color
    def __enter__(self):
        self.led.set_color(self.color)
    def __exit__(self, *args):
        self.led.off()


class LedIndicator:
    class RGBLeds:
        def __init__(self, red_gpio, green_gpio, blue_gpio):
            self.rgb_pins = [PWM(Pin(gpio)) for gpio in (red_gpio, green_gpio, blue_gpio)]
            for pwm in self.rgb_pins:
                pwm.freq(100)
                pwm.duty_u16(0)
            self._current_task = None
            self.off()
        
        def change_color_rgb(self, r_255, g_255, b_255):
            u16_values = [int(v * _U16 / 255) for v in (r_255, g_255, b_255)]
            for pwm, u16_v in zip(self.rgb_pins, u16_values):
                pwm.duty_u16(u16_v)

    class NeoPixel:
        def __init__(self, di_gpio):
            self.np = neopixel.NeoPixel(Pin(di_gpio), 1)
        
        def change_color_rgb(self, r_255, g_255, b_255):
            self.np[0] = (r_255, g_255, b_255)
            self.np.write()

    @classmethod
    def from_rgb_leds(cls, *args, **kwargs):
        return cls(cls.RGBLeds(*args, **kwargs))
    
    @classmethod
    def from_neo_pixel(cls, *args, **kwargs):
        return cls(cls.NeoPixel(*args, **kwargs))

    def __init__(self, leds):
        self.leds = leds
        self.intensity = 0

    def set_intensity(self, intensity):
        self.intensity = intensity

    def set_color(self, color_name):
        if color_name not in _RGB_COLORS:
            raise ValueError(f"Unknown color '{color_name}'.")
        r_255, g_255, b_255 = _RGB_COLORS[color_name]
        r_255, g_255, b_255 = [(val >> -self.intensity) for val in (r_255, g_255, b_255)]
        self.leds.change_color_rgb(r_255, g_255, b_255)
    
    def off(self):
        self.leds.change_color_rgb(0, 0, 0)

    async def blink(self, color, cycle_ms=200, times=None):
        ctr = 0
        while True:
            if times is not None and ctr >= times:
                break
            self.set_color(color)
            await asyncio.sleep_ms(cycle_ms // 2)
            self.off()
            if times is None or ctr != times - 1:  # No need to wait at the last cycle
                await asyncio.sleep_ms(cycle_ms // 2)
            ctr += 1
  
    def blink_sync(self, color, cycle_ms=200, times=None):
        asyncio.run(self.blink(color, cycle_ms, times))

    def indicate(self, color):
        return LedIndicate(self, color)
