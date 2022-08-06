import uasyncio as asyncio
import wave

from machine import I2S, Pin

EVENT_AUDIO_STARTED = 1
EVENT_AUDIO_FINISHED = 2


def _assert_wav_file(filename):
    if not filename.lower().endswith(".wav"):
        raise ValueError(f"Illegal filename '{filename}'. Only WAVs are supported.")


class AudioPlayer:
    def __init__(self, config):
        self.i2s_id = config["I2S_id"]
        self.gpio_sck = config["I2S_SCK"]
        self.gpio_ws = config["I2S_WS"]
        self.gpio_sd = config["I2S_SD"]
        self.buffer_length_bytes = config["I2S_buffer_length_bytes"]

        self.activity_listener_callbacks = []

        self._currently_playing_task = None

        wav_samples = bytearray(self.buffer_length_bytes)
        self.wav_samples_mv = memoryview(wav_samples)

    def register_activity_callback(self, callback_func):
        self.activity_listener_callbacks.append(callback_func)

    def _notify_listeners(self, event):
        for callback_func in self.activity_listener_callbacks:
            callback_func(event)

    async def _play_file_async(self, wav_filename):
        _assert_wav_file(wav_filename)

        # Read WAV properties
        with wave.open(wav_filename) as f:
            wav_frame_rate = f.getframerate()
            wav_num_channels = f.getnchannels()
            wav_sample_width_bits = 8 * f.getsampwidth()
        
        # Create I2S for this file
        audio_out = I2S(
            self.i2s_id,
            sck=Pin(self.gpio_sck),
            ws=Pin(self.gpio_ws),
            sd=Pin(self.gpio_sd),
            mode=I2S.TX,
            bits=wav_sample_width_bits,
            format=I2S.MONO if wav_num_channels == 1 else I2S.STEREO,
            rate=wav_frame_rate,
            ibuf=self.buffer_length_bytes,
        )

        try :
            self._notify_listeners(EVENT_AUDIO_STARTED)

            swriter = asyncio.StreamWriter(audio_out)
            # allocate sample array
            # memoryview used to reduce heap allocation
            
            with open(wav_filename, "rb") as wav:
                _ = wav.seek(44)  # advance to first byte of Data section in WAV file

                while True:
                    num_read = wav.readinto(self.wav_samples_mv)
                    if num_read == 0:
                        # End of file.
                        return
                    else:
                        # apply temporary workaround to eliminate heap allocation in uasyncio Stream class.
                        # workaround can be removed after acceptance of PR:
                        #    https://github.com/micropython/micropython/pull/7868
                        # swriter.write(wav_samples_mv[:num_read])
                        swriter.out_buf = self.wav_samples_mv[:num_read]
                        await swriter.drain()
        finally:
            # cleanup
            audio_out.deinit()    
            self._notify_listeners(EVENT_AUDIO_FINISHED)

    def stop(self):
        if self._currently_playing_task is not None:
            self._currently_playing_task.cancel()
        self._currently_playing_task = None

    def play_file(self, filename):
        self.stop()
        self._currently_playing_task = asyncio.create_task(self._play_file_async(filename))


    # # def increase_volume(self):
    # #     current_volume = self.get_volume()
    # #     new_volume = min(100, round(current_volume + self.volume_step, -1))
    # #     self.set_volume(new_volume)

    # # def decrease_volume(self):
    # #     current_volume = self.get_volume()
    # #     new_volume = max(0, round(current_volume - self.volume_step, -1))
    # #     self.set_volume(new_volume)

    # # def set_volume(self, volume):
    # #     self.mixer.setvolume(int(max(0, min(100, volume))))

    # # def get_volume(self):
    # #     vs = self.mixer.getvolume()
    # #     return sum(vs) / len(vs)  # Averaging on channels.