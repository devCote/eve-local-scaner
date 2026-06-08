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
    ACCENT_ENABLE_BLURBEHIND = 3
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

    _SetWindowCompositionAttribute = ctypes.windll.user32.SetWindowCompositionAttribute
    _SetWindowCompositionAttribute.restype = wintypes.BOOL
    _SetWindowCompositionAttribute.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
    ]


def is_windows_blur_supported() -> bool:
    return sys.platform == "win32"


def _apply_accent(hwnd: int, state: int, gradient_color: int = 0) -> bool:
    if sys.platform != "win32":
        return False

    try:
        accent = ACCENT_POLICY()
        accent.AccentState = state
        accent.AccentFlags = 0
        accent.GradientColor = gradient_color
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        ok = _SetWindowCompositionAttribute(int(hwnd), ctypes.byref(data))
        return bool(ok)
    except Exception as e:
        print("Windows blur error:", e)
        return False


def disable_eve_blur(hwnd: int) -> bool:
    return _apply_accent(hwnd, ACCENT_DISABLED, 0)


def enable_eve_blur(hwnd: int, alpha: int = 175, blur_percent: int = 35, bg_color=(7, 8, 10)) -> bool:
    """
    Enables Windows acrylic/blur-behind for the Qt window.

    Important: Windows AccentPolicy does not expose a true blur-radius control.
    The blur layer itself is fixed by Windows. To make the Options slider feel
    gradual, blur_percent controls the acrylic tint strength:

    0   = blur/acrylic disabled
    1   = almost transparent acrylic tint
    100 = strongest acrylic tint

    alpha is kept for compatibility, but the visible blur intensity is derived
    from blur_percent so the slider no longer behaves like simple on/off.
    """
    if sys.platform != "win32":
        return False

    blur_percent = max(0, min(100, int(blur_percent)))

    if blur_percent <= 0:
        return disable_eve_blur(hwnd)

    r, g, b = bg_color

    # Windows acrylic blur radius is fixed. The only practical continuous
    # control is the tint alpha. Keep the low end VERY soft: earlier 1%
    # already looked too strong because tint_alpha was forced up by window alpha.
    #
    # 1%   -> alpha 1
    # 50%  -> alpha ~45
    # 100% -> alpha ~120
    curve = (blur_percent / 100) ** 1.35
    tint_alpha = int(round(1 + curve * 119))
    tint_alpha = max(1, min(160, tint_alpha))

    # Windows expects AABBGGRR.
    gradient_color = (tint_alpha << 24) | (int(b) << 16) | (int(g) << 8) | int(r)

    # Acrylic has the nicest Windows 10/11 blur. If it fails, fallback to blur-behind.
    if _apply_accent(hwnd, ACCENT_ENABLE_ACRYLICBLURBEHIND, gradient_color):
        return True

    return _apply_accent(hwnd, ACCENT_ENABLE_BLURBEHIND, gradient_color)
