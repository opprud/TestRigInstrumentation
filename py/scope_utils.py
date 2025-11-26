import json
import socket
import time
import os
import pyvisa

SCOPE_CACHE_FILE = "scope_cache.json"

DEFAULT_PORT_LIST = [5025, 5555, 4000, 4980]
DEFAULT_HOST_CANDIDATES = [
    "msox-2024a",
    "scope",
    "scope.local",
    "msox.local",
]

SCAN_SUBNETS = [
    "192.168.0.",
    "192.168.1.",
    "10.0.0.",
]


# ------------------- BaseScope -------------------

class BaseScope:
    """
    Ensartet API for socket og VISA scopes.
    Skal understøtte:
        write(cmd)
        query(cmd)
        query_binary(cmd)
        idn()
    """

    def write(self, cmd: str):
        raise NotImplementedError

    def query(self, cmd: str) -> str:
        raise NotImplementedError

    def query_binary(self, cmd: str) -> bytes:
        raise NotImplementedError

    def idn(self):
        try:
            return self.query("*IDN?")
        except:
            return "UNKNOWN"


# ------------------- SocketScope -------------------

class SocketScope(BaseScope):
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def _open(self):
        return socket.create_connection((self.host, self.port), timeout=3.0)

    def write(self, cmd: str):
        s = self._open()
        try:
            s.sendall((cmd + "\n").encode("ascii"))
        finally:
            s.close()

    def query(self, cmd: str) -> str:
        s = self._open()
        try:
            s.sendall((cmd + "\n").encode("ascii"))
            data = s.recv(65536)
            return data.decode(errors="ignore")
        finally:
            s.close()

    def query_binary(self, cmd: str) -> bytes:
        s = self._open()
        try:
            s.sendall((cmd + "\n").encode("ascii"))
            chunks = []
            while True:
                buf = s.recv(65536)
                if not buf:
                    break
                chunks.append(buf)
            return b"".join(chunks)
        finally:
            s.close()


# ------------------- VisaScope -------------------

class VisaScope(BaseScope):
    def __init__(self, resource):
        self.resource = resource
        rm = pyvisa.ResourceManager()
        self.dev = rm.open_resource(resource)
        self.dev.timeout = 5000

    def write(self, cmd: str):
        self.dev.write(cmd)

    def query(self, cmd: str) -> str:
        return self.dev.query(cmd)

    def query_binary(self, cmd: str) -> bytes:
        return bytes(self.dev.query_binary_values(cmd, datatype='B', container=bytearray))


# ------------------- Helper functions -------------------

def load_cache():
    if not os.path.exists(SCOPE_CACHE_FILE):
        return None
    try:
        with open(SCOPE_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def save_cache(host, port):
    try:
        with open(SCOPE_CACHE_FILE, "w") as f:
            json.dump({"host": host, "port": port}, f)
    except:
        pass


def try_connect_socket(host, port):
    try:
        s = socket.create_connection((host, port), timeout=1.5)
        s.close()
        return True
    except:
        return False


def scan_for_scopes(port_list):
    for subnet in SCAN_SUBNETS:
        for i in range(1, 255):
            ip = subnet + str(i)
            for p in port_list:
                if try_connect_socket(ip, p):
                    return ip, p
    return None, None


def detect_visa_scopes():
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        for res in resources:
            if "MSO" in res.upper() or "USB" in res.upper() or "TCPIP" in res.upper():
                return res
    except:
        pass
    return None


# ------------------- ScopeManager -------------------

class ScopeManager:
    """
    Autodetect i denne rækkefølge:

    1) cache → host+port
    2) config.json override-port + host candidates
    3) VISA device
    4) network scan
    """

    def __init__(self, preferred_port=None):

        self.scope = None
        self.host = None
        self.port = None

        # Brug config port override (hvis sat)
        if preferred_port:
            self.port_list = [preferred_port]
        else:
            self.port_list = DEFAULT_PORT_LIST

        # 1) Cache
        cache = load_cache()
        if cache:
            h = cache.get("host")
            p = cache.get("port")
            if h and p:
                if try_connect_socket(h, p):
                    self.scope = SocketScope(h, p)
                    self.host, self.port = h, p
                    return

        # 2) Manual host candidates (scope.local osv.)
        for host in DEFAULT_HOST_CANDIDATES:
            for p in self.port_list:
                if try_connect_socket(host, p):
                    self.scope = SocketScope(host, p)
                    self.host, self.port = host, p
                    save_cache(host, p)
                    return

        # 3) VISA
        visa_res = detect_visa_scopes()
        if visa_res:
            try:
                self.scope = VisaScope(visa_res)
                self.host, self.port = visa_res, "VISA"
                save_cache(visa_res, "VISA")
                return
            except:
                pass

        # 4) Full network scan
        host, p = scan_for_scopes(self.port_list)
        if host and p:
            self.scope = SocketScope(host, p)
            self.host, self.port = host, p
            save_cache(host, p)
            return

    # Wrapper API så acquire_scope_data.py kan kalde dette direkte
    def write(self, cmd: str):
        return self.scope.write(cmd)

    def query(self, cmd: str):
        return self.scope.query(cmd)

    def query_binary(self, cmd: str):
        return self.scope.query_binary(cmd)

    def idn(self):
        return self.scope.idn() if self.scope else "NO_SCOPE"
