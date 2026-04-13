import esp32
import network
import time
import webrepl


NAMESPACE = "secrets"
BUFFER_SIZE = 128


def read_secret(nvs, key):
    buf = bytearray(BUFFER_SIZE)
    try:
        length = nvs.get_blob(key, buf)
    except OSError:
        return None
    return buf[:length].decode("utf-8")


def load_config():
    nvs = esp32.NVS(NAMESPACE)
    ssid = read_secret(nvs, "ssid")
    wifi_password = read_secret(nvs, "wifipw")
    webrepl_password = read_secret(nvs, "replpw")

    if not ssid or webrepl_password is None:
        raise RuntimeError("NVS is not configured. Run setup.py over serial first.")

    size = len(webrepl_password.encode("utf-8"))
    if size == 0 or size > 8:
        raise RuntimeError("Invalid WebREPL password in NVS.")

    return ssid, wifi_password or "", webrepl_password


def connect_wifi(ssid, password, timeout_ms=15000):
    sta = network.WLAN(network.STA_IF)
    if not sta.active():
        sta.active(True)
    if sta.isconnected():
        return

    sta.connect(ssid, password)
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while not sta.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("Wi-Fi connect timeout")
        time.sleep_ms(200)


def main():
    ssid, wifi_password, webrepl_password = load_config()
    connect_wifi(ssid, wifi_password)
    try:
        webrepl.start(password=webrepl_password)
    except Exception as exc:
        raise RuntimeError("WebREPL start failed: {}".format(exc))


try:
    main()
except RuntimeError as exc:
    message = str(exc)
    if "Wi-Fi" in message:
        print("Wi-Fi setup failed:", message)
    elif "WebREPL" in message:
        print(message)
    else:
        print("WebREPL setup skipped:", message)
except Exception as exc:
    print("WebREPL start failed:", exc)
