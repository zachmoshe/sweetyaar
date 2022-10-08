import time
import machine
import network
import urequests as requests 
import gc

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzWfpxx6mPyE1Izgnn2vsO7yK-mTN4OwV1gViEiudet2-udyCcEsYXv2F9cf4ZocT7O/exec"

def submit_measurement(read_u16, read_uv):
    _time = time.localtime()
    time_str = ":".join(str(x) for x in time.localtime()[3:6])

    gc.collect()
    res = requests.get(f"{SCRIPT_URL}?time={time.time()}&time_str={time_str}&read_u16={read_u16}&read_uv={read_uv}")
    if res.status_code != 200:
        raise Exception(f"Couldn't submit measurements: [{res.status_code}] {res.reason}")
    print(f"{read_u16}, {read_uv} - submitted successfully at {time_str}.")
    res.close()


sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
sta_if.connect("ZachMoshe", "PASSWORD HERE")

while not sta_if.isconnected():
    time.sleep(0.1)
print("WiFi connected!", sta_if.ifconfig())

anl = machine.ADC(machine.Pin(34))
anl.atten(machine.ADC.ATTN_11DB)

while True:
    try:
        read_u16 = anl.read_u16()
        read_uv = anl.read_uv()
        submit_measurement(read_u16, read_uv)    
        time.sleep(60)
    except Exception as e:
        submit_measurement(e, e.message)
