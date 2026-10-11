"""Read a named Windows Credential Manager secret into process memory only."""
import ctypes
from ctypes import wintypes
import os


def read_windows_credential(target: str) -> str:
    if os.name != "nt" or not target or len(target) > 256:
        raise ValueError("Named Windows credential unavailable")

    class Credential(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    pointer = ctypes.POINTER(Credential)()
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        raise ValueError("Named Windows credential unavailable")
    try:
        item = pointer.contents
        blob = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        # Windows clients commonly store UTF-16LE; keyring implementations may store UTF-8.
        encoding = "utf-16-le" if b"\x00" in blob else "utf-8"
        password = blob.decode(encoding).rstrip("\x00")
        if not password:
            raise ValueError("Named Windows credential is empty")
        return password
    finally:
        api.CredFree(pointer)


def resolve_passwords():
    for prefix in ("MCP_DB",):
        name = f"{prefix}_PASSWORD"
        target = os.environ.get(f"{name}_CREDENTIAL")
        if target:
            if os.environ.get(name):
                raise ValueError("Choose environment password or named credential, not both")
            os.environ[name] = read_windows_credential(target)
