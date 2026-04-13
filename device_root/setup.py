import esp32


NAMESPACE = "secrets"
FIELDS = (
    ("ssid", "Wi-Fi SSID", True, 32),
    ("wifipw", "Wi-Fi password", False, 64),
    ("replpw", "WebREPL password", True, 8),
)


def validate(name, value, required, max_bytes):
    if not isinstance(value, str):
        raise ValueError("{} must be a string".format(name))

    size = len(value.encode("utf-8"))
    if required and size == 0:
        raise ValueError("{} must not be empty".format(name))
    if size > max_bytes:
        raise ValueError("{} must be {} byte(s) or less".format(name, max_bytes))


def prompt_value(name, required, max_bytes):
    while True:
        value = input("{}: ".format(name))
        try:
            validate(name, value, required, max_bytes)
            return value
        except ValueError as exc:
            print(exc)


def main():
    nvs = esp32.NVS(NAMESPACE)

    print("--- WebREPL setup ---")
    for key, name, required, max_bytes in FIELDS:
        value = prompt_value(name, required, max_bytes)
        nvs.set_blob(key, value.encode("utf-8"))
        print("{} saved.".format(name))

    nvs.commit()
    print("Saved to NVS. Reset the board to start WebREPL.")


main()
