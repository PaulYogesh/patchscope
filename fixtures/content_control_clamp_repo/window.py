def moving_window(values, width):
    if width < 1:
        raise ValueError("Window must be positive")
    return [values[i:i + width] for i in range(0, len(values), width)]
