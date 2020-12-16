from socket import *
import threading
from network_common import *

class UDPClient:
    def __init__(self, host, port=37001, override_uuid=None):
        self.AUDIO_QUEUE = Queue()
        self.VIDEO_QUEUE = Queue()
        self.INFO_QUEUE = Queue()

        self.host = host
        self.port = port

        self.socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        self.socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        # I NEED A REALLY RANDOM PORT SO I CAN RECEIVE - ROUTER HAS NAT, WE'RE RECEIVING FROM WAN, NUM DOESNT MATTER
        p = 38000
        while True:
            try:
                self.socket.bind(('', p))
            except OSError:
                continue
            else:
                break

        self.session = UDPSession(self, self.host, self.port)
        if override_uuid:
            self.session.uuid = override_uuid
        self.session.start_send_thread()

        self.running = False
        self.thread = threading.Thread(target=self._handle_data, daemon=True)

    def init(self):
        self.running = True
        self.thread.start()
    def close(self):
        self.running = False
        self.socket.close()

    def _handle_data(self):
        while self.running:
            data = UDPSession.decompile(self.socket.recvfrom(50000)[0])

            if not self.session.verify_pid(data[1]):
                print('Out of order packet rejected')
                continue
            self.session.packet_id_recv = data[1]

            if data[2] == 'INFO': # DATATYPE
                self.INFO_QUEUE.put((data[0], data[3]))
            elif data[2] == 'AUDIO':
                self.AUDIO_QUEUE.put((data[0], data[3]))
            elif data[2] == 'VIDEO':
                self.VIDEO_QUEUE.put((data[0], data[3]))
            elif data[2] == 'KEEPALIVE':
                pass
            elif data[2] == 'PRINT':
                print('PRINT REQUEST:', data[3])
            else:
                ...  # can do stuff if necessary
