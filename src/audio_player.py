import uasyncio as asyncio
import wave

from machine import I2S, Pin
from micropython import const

from src import bt_logger

_logger = bt_logger.get_logger(__name__)

_SILENT_BYTES = bytearray(1024)

EVENT_AUDIO_STARTED = const(1)
EVENT_AUDIO_FINISHED = const(2)

_WAV_SAMPLE_BITS = const(16)
_WAV_NUM_CHANNELS = const(1)
_WAV_SAMPLE_RATE = const(22050)


def _assert_wav_file(filename):
    if not filename.lower().endswith(".wav"):
        raise ValueError(f"Illegal filename '{filename}'. Only WAVs are supported.")
    
    # Read WAV properties
    with wave.open(filename) as f:
        wav_frame_rate = f.getframerate()
        wav_num_channels = f.getnchannels()
        wav_sample_width_bits = 8 * f.getsampwidth()
    
        if (wav_frame_rate != _WAV_SAMPLE_RATE) or (wav_num_channels != _WAV_NUM_CHANNELS) or (wav_sample_width_bits != _WAV_SAMPLE_BITS):
            raise ValueError(
                f"Illegal WAV file ({filename}). Expected (sample_rate={_WAV_SAMPLE_RATE}, {_WAV_NUM_CHANNELS} channels x {_WAV_SAMPLE_BITS} bits/sample), Got (sample_rate={wav_frame_rate}, {wav_num_channels} channels x {wav_sample_width_bits} bits/sample).")



class AudioPlayer:
    def __init__(self, config, preallocated_buffer):
        self.i2s_id = config["I2S_id"]
        self.gpio_sck = config["I2S_SCK"]
        self.gpio_ws = config["I2S_WS"]
        self.gpio_sd = config["I2S_SD"]
        self.buffer_length_bytes = config["I2S_buffer_length_bytes"]

        self.activity_listener_callbacks = []

        self.volume = 0  # The shift in bits. 0 means untouched. None means muted
        self._currently_playing_task = None
        self._input_file_handle = None
        self._silent_samples = _SILENT_BYTES
        self._wav_samples = memoryview(preallocated_buffer)

        self.audio_out = I2S(
            self.i2s_id,
            sck=Pin(self.gpio_sck),
            ws=Pin(self.gpio_ws),
            sd=Pin(self.gpio_sd),
            mode=I2S.TX,
            bits=_WAV_SAMPLE_BITS,
            format=(I2S.MONO if _WAV_NUM_CHANNELS == 1 else I2S.STEREO),
            rate=_WAV_SAMPLE_RATE,
            ibuf=self.buffer_length_bytes,
        ) 
        asyncio.create_task(self._play_loop())


    async def _play_loop(self):
        swriter = asyncio.StreamWriter(self.audio_out)

        while True:
            try:
                if self._input_file_handle is None:
                    swriter.out_buf = self._silent_samples
                    await swriter.drain()

                else:
                    num_read = self._input_file_handle.readinto(self._wav_samples)
                    if num_read == 0:  # EOF 
                        self.stop()
                    else:
                        # apply temporary workaround to eliminate heap allocation in uasyncio Stream class.
                        # workaround can be removed after acceptance of PR:
                        #    https://github.com/micropython/micropython/pull/7868
                        # swriter.write(wav_samples_mv[:num_read])
                        if self.volume is None:  # muted
                            swriter.out_buf = self._silent_samples
                        else:
                            if self.volume != 0:
                                I2S.shift(buf=self._wav_samples, bits=_WAV_SAMPLE_BITS, shift=self.volume)
                            swriter.out_buf = self._wav_samples[:num_read]
                        await swriter.drain()
            except Exception as e:
                _logger.error(f"EXCEPTION IN PLAYER: {repr(e)}")
                self.stop()
                raise e


    def play_file(self, wav_filename, desc=""):
        _assert_wav_file(wav_filename)
        self.stop()  # make sure filehandle is closed.
        self._notify_listeners(EVENT_AUDIO_STARTED, desc)

        fh = open(wav_filename, "rb")
        fh.seek(44)
        self._input_file_handle = fh

    def stop(self):
        if self._input_file_handle is not None:
            self._input_file_handle.close()
            self._input_file_handle = None
        self._notify_listeners(EVENT_AUDIO_FINISHED)

    @property
    def is_playing(self):
        return self._input_file_handle is not None

    def register_activity_callback(self, callback_func):
        self.activity_listener_callbacks.append(callback_func)

    def _notify_listeners(self, event, *args):
        for callback_func in self.activity_listener_callbacks:
            callback_func(event, *args)
