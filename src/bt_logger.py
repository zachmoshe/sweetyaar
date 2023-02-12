import json
import time 

import aioble
from micropython import const


_DEFAULT_LOG_FORMAT = const("{localtime_year}/{localtime_month:02.n}/{localtime_day:02.n} {localtime_hours:02.n}:{localtime_minutes:02.n}:{localtime_seconds:02.n} [{severity}][{name}] {message}")
_DEFAULT_NUM_LAST_MESSAGES = const(20)

_LOGLEVEL_DEBUG = const("D")
_LOGLEVEL_INFO = const("I")
_LOGLEVEL_WARN = const("W")
_LOGLEVEL_ERROR = const("E")

_LOGGER = None
def get_logger(name = None, message_format=_DEFAULT_LOG_FORMAT, num_last_messages=_DEFAULT_NUM_LAST_MESSAGES):
    global _LOGGER
    name = name or __name__
    if _LOGGER is None:
        _LOGGER = _BTLogger(message_format, num_last_messages)

    return _LOGGER.get_module_logger(name)


class _BTLogger:

    class _BTModuleLogger:
        def __init__(self, bt_logger, name):
            self.name = name
            self.bt_logger = bt_logger

        def _generate_message_string(self, localtime_tuple, message, severity):
            localtime_year, localtime_month, localtime_day, localtime_hours, localtime_minutes, localtime_seconds, *_ = localtime_tuple
            return self.bt_logger.message_format.format(
                localtime_year=localtime_year, localtime_month=localtime_month, localtime_day=localtime_day, 
                localtime_hours=localtime_hours, localtime_minutes=localtime_minutes, localtime_seconds=localtime_seconds, 
                severity=severity, name=self.name, message=message)

        def debug(self, message):
            msg = self._generate_message_string(time.localtime(), message, _LOGLEVEL_DEBUG)
            self.bt_logger._log_message(msg)

        def info(self, message):
            msg = self._generate_message_string(time.localtime(), message, _LOGLEVEL_INFO)
            self.bt_logger._log_message(msg)

        def warn(self, message):
            msg = self._generate_message_string(time.localtime(), message, _LOGLEVEL_WARN)
            self.bt_logger._log_message(msg)

        def error(self, message):
            msg = self._generate_message_string(time.localtime(), message, _LOGLEVEL_ERROR)
            self.bt_logger._log_message(msg)


    def __init__(self, message_format, num_last_messages):
        self.message_format = message_format
        self.num_last_messages = num_last_messages
        self._bt_characteristic = None

    def get_module_logger(self, name):
        return _BTLogger._BTModuleLogger(self, name)

    def _notify_bt_clients(self, message):
        self._bt_characteristic.write(message.encode("utf8"), send_update=True)

    def _log_message(self, msg_string):
        print(msg_string)
        if self._bt_characteristic is not None:
            self._notify_bt_clients(msg_string)
    
    def connect_to_bt_characteristic(self, bt_char):
        self._bt_characteristic = bt_char

