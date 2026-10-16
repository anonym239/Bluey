"""Macht den PC im WLAN bekannt (Bonjour/mDNS `_googly._tcp`) und schickt Gesichts-Updates an jedes verbundene Handy.

Gleiches Protokoll wie die Mac-App: iPhone und Android können sich verbinden.
"""
import socket
import threading
import time
from collections import deque

from .protocol import SERVICE_TYPE, Decoder, encode


def lan_addresses():
    """IPv4-Adressen dieses PCs im lokalen Netz (ohne Internet zu brauchen)."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))  # sendet nichts, wählt nur die Standard-Schnittstelle
        found.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith(("127.", "169.254.")))


class Phone:
    def __init__(self, sock, address):
        self.sock, self.address = sock, address
        self.name = None
        self.lock = threading.Lock()
        self.alive = True
        self.queue = deque()
        self.ready = threading.Event()

    def send(self, packet):
        if not self.alive:
            return
        data = encode(packet)
        with self.lock:
            self.queue.append(data)
        self.ready.set()


class PhoneServer:
    def __init__(self, name=None, port=52700):
        self.name = name or socket.gethostname()
        self.wanted_port = port
        self.port = None
        self.phones = []
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._listener = None
        self._zeroconf = None
        self._info = None
        self._last_face = None
        self._last_face_at = 0.0
        self.on_phones_changed = lambda names: None
        # Ein Handy will etwas: (Paket, Antwort-Funktion, Handy). Läuft auf dem Lese-Thread des Handys.
        self.on_request = lambda packet, reply, phone: None
        self.on_disconnect = lambda phone: None

    @property
    def phone_names(self):
        with self._lock:
            return [p.name or "Handy" for p in self.phones]

    def start(self):
        self._stopped.clear()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("0.0.0.0", self.wanted_port))
        except OSError:
            listener.bind(("0.0.0.0", 0))  # fester Port belegt: irgendeinen nehmen
        listener.listen(8)
        listener.settimeout(0.5)
        self._listener = listener
        self.port = listener.getsockname()[1]
        threading.Thread(target=self._accept, name="Bluey Annahme", daemon=True).start()
        threading.Thread(target=self._advertise, name="Bluey Bonjour", daemon=True).start()
        return self.port

    def _advertise(self):
        try:
            from zeroconf import ServiceInfo, Zeroconf
            addresses = lan_addresses()
            if not addresses:
                return
            host = socket.gethostname().split(".")[0]
            info = ServiceInfo(SERVICE_TYPE, f"{self.name}.{SERVICE_TYPE}",
                               addresses=[socket.inet_aton(a) for a in addresses], port=self.port,
                               properties={"app": "bluey-windows"}, server=f"{host}.local.")
            zc = Zeroconf()
            zc.register_service(info, allow_name_change=True)
            self._zeroconf, self._info = zc, info
        except Exception:
            self._zeroconf = None

    def _accept(self):
        while not self._stopped.is_set():
            try:
                sock, address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.settimeout(1.0)
            phone = Phone(sock, address)
            with self._lock:
                if len(self.phones) >= 8:
                    sock.close()
                    continue
                self.phones.append(phone)
            phone.send({"hello": self.name})
            if self._last_face:
                phone.send({"face": self._last_face})
            threading.Thread(target=self._read, args=(phone,), name="Bluey Handy lesen", daemon=True).start()
            threading.Thread(target=self._write, args=(phone,), name="Bluey Handy schreiben", daemon=True).start()
            self.on_phones_changed(self.phone_names)

    def _write(self, phone):
        while phone.alive and not self._stopped.is_set():
            phone.ready.wait(0.5)
            with phone.lock:
                items = list(phone.queue)
                phone.queue.clear()
                phone.ready.clear()
            if not items:
                continue
            try:
                phone.sock.sendall(b"".join(items))
            except OSError:
                self._drop(phone)

    def _read(self, phone):
        decoder = Decoder()
        try:
            while phone.alive and not self._stopped.is_set():
                try:
                    data = phone.sock.recv(262144)
                except socket.timeout:
                    continue
                if not data:
                    break
                for packet in decoder.feed(data):
                    if "hello" in packet and isinstance(packet["hello"], str):
                        phone.name = packet["hello"][:120]
                        self.on_phones_changed(self.phone_names)
                    if packet.get("command"):
                        def reply(response, phone=phone):
                            phone.send(response)
                        try:
                            self.on_request(packet, reply, phone)
                        except Exception:
                            pass
        except (OSError, ValueError):
            pass
        finally:
            self._drop(phone)

    def _drop(self, phone):
        with self._lock:
            if phone not in self.phones:
                return
            self.phones.remove(phone)
        phone.alive = False
        phone.ready.set()
        try:
            phone.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        phone.sock.close()
        self.on_disconnect(phone)
        self.on_phones_changed(self.phone_names)

    def broadcast(self, packet):
        """Schickt einen Befehl an jedes Handy (z. B. "wake", "sleep")."""
        with self._lock:
            phones = list(self.phones)
        for phone in phones:
            phone.send(packet)

    def send_face(self, face):
        """Schickt das Gesicht an alle Handys und überspringt zu kleine Änderungen."""
        # Mindestens einmal pro Sekunde, damit das Handy weiß, dass der PC noch steuert.
        t = time.monotonic()
        last = self._last_face
        if last and t - self._last_face_at < 1 and last["mood"] == face["mood"] \
                and abs(last["gazeX"] - face["gazeX"]) < 0.004 and abs(last["gazeY"] - face["gazeY"]) < 0.004 \
                and abs(last["talk"] - face["talk"]) < 0.02:
            return
        self._last_face, self._last_face_at = dict(face), t
        self.broadcast({"face": face})

    def stop(self):
        self._stopped.set()
        if self._zeroconf:
            try:
                self._zeroconf.unregister_service(self._info)
                self._zeroconf.close()
            except Exception:
                pass
            self._zeroconf = None
        if self._listener:
            self._listener.close()
        with self._lock:
            phones = list(self.phones)
        for phone in phones:
            self._drop(phone)
