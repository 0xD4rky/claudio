import sounddevice as sd


def resolve_device(name: str | None) -> int | None:
    if name is None:
        return None
    if name.isdigit():
        return int(name)
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and name.lower() in d["name"].lower():
            return i
    return None
