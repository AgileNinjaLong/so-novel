import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtCore import QObject, pyqtSignal, QAbstractNativeEventFilter, QCoreApplication

# Win32 Hotkey Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

VK_MAP = {
    'z': 0x5A, 'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
    'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C, 'm': 0x4D,
    'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'esc': 0x1B, 'space': 0x20
}

class WindowsNativeHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id, callback):
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b'windows_generic_MSG':
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                self.callback()
                return True, 0
        return False, 0

class BossKeyManager(QObject):
    triggered = pyqtSignal()

    def __init__(self, key_combination: str = "Alt+Z"):
        super().__init__()
        self.key_combination = key_combination
        self.is_active = False
        self._filter = None
        self._hotkey_id = 1001

    def start(self):
        if sys.platform == "win32":
            try:
                mod, vk = self._parse_shortcut(self.key_combination)
                user32 = ctypes.windll.user32
                if user32.RegisterHotKey(None, self._hotkey_id, mod, vk):
                    self._filter = WindowsNativeHotkeyFilter(self._hotkey_id, self._on_triggered)
                    QCoreApplication.instance().installNativeEventFilter(self._filter)
                    self.is_active = True
                    return
            except Exception:
                pass

        # Fallback to keyboard library
        try:
            import keyboard
            hk = self.key_combination.lower().replace("alt", "alt").replace("ctrl", "ctrl")
            keyboard.add_hotkey(hk, self._on_triggered)
            self.is_active = True
        except Exception:
            self.is_active = False

    def _parse_shortcut(self, shortcut: str):
        parts = [p.strip().lower() for p in shortcut.split('+')]
        mod = 0
        vk = 0
        for p in parts:
            if p == 'alt':
                mod |= MOD_ALT
            elif p in ('ctrl', 'control'):
                mod |= MOD_CONTROL
            elif p == 'shift':
                mod |= MOD_SHIFT
            elif p == 'win':
                mod |= MOD_WIN
            elif p in VK_MAP:
                vk = VK_MAP[p]
            elif len(p) == 1:
                vk = ord(p.upper())
        return mod, vk

    def _on_triggered(self):
        self.triggered.emit()

    def stop(self):
        if sys.platform == "win32" and self.is_active and self._filter:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
                QCoreApplication.instance().removeNativeEventFilter(self._filter)
            except Exception:
                pass
        try:
            import keyboard
            keyboard.remove_hotkey(self._on_triggered)
        except Exception:
            pass
