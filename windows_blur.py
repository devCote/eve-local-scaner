import sys


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
        ]

    class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    WCA_ACCENT_POLICY = 19
    ACCENT_DISABLED = 0
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

    _SetWindowCompositionAttribute = ctypes.windll.user32.SetWindowCompositionAttribute
    _SetWindowCompositionAttribute.restype = wintypes.BOOL
    _SetWindowCompositionAttribute.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
    ]


def _gradient_color(alpha: int, rgb: tuple[int, int, int]) -> int:
    alpha = max(0, min(255, int(alpha)))
    r, g, b = rgb
    # Windows expects AABBGGRR.
    return (alpha << 24) | (b << 16) | (g << 8) | r


def _apply_accent(hwnd: int, accent_state: int, alpha: int = 0, rgb=(11, 11, 11)) -> bool:
    if sys.platform != "win32":
        return False

    try:
        accent = ACCENT_POLICY()
        accent.AccentState = int(accent_state)
        accent.AccentFlags = 0
        accent.GradientColor = _gradient_color(alpha, rgb)
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        return bool(_SetWindowCompositionAttribute(int(hwnd), ctypes.byref(data)))

    except Exception as e:
        print("Windows blur error:", e)
        return False


def enable_eve_blur(hwnd: int, panel_alpha: int = 230, blur_percent: int = 0, rgb=(11, 11, 11)) -> bool:
    blur_percent = max(0, min(100, int(blur_percent)))
    panel_alpha = max(0, min(255, int(panel_alpha)))

    if blur_percent <= 0:
        # Important: do not use TRANSPARENTGRADIENT at startup.
        # It can tint the first frame on some Windows/Qt setups.
        return _apply_accent(hwnd, ACCENT_DISABLED)

    return _apply_accent(
        hwnd,
        ACCENT_ENABLE_ACRYLICBLURBEHIND,
        max(40, min(220, panel_alpha)),
        rgb,
    )
