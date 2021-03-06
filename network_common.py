from uuid import getnode
from queue import Queue
from threading import Thread
from collections import defaultdict
from socket import socket
from typing import Optional
import struct

FRAG_LIMIT = 8000

class Session:
    def __init__(self, manager, ip, port, tcp_socket: Optional[socket], uuid=None, fragment=False):
        self.manager = manager  # UDPClient or UDPManager will both work
        self.ip = ip
        self.port = port
        self.uuid = uuid or str(getnode())
        self.frag = fragment

        self.tcp_socket = tcp_socket
        self.tcp_send_buffer = Queue()
        self.tcp_recv_thread = Thread(target=self._recv_all_tcp, daemon=True)
        self.tcp_send_thread = Thread(target=self._send_all_tcp, daemon=True)

        # these are different because we don't care about client and server syncing perfectly when it's just streaming data
        # all we want to ensure is that we and they are not *receiving* packets out of order, and are discarding such packets
        # access by datatype
        self.packet_id_send = defaultdict(lambda: -1)  # packet id of packets we receive - other end's send id
        self.packet_id_recv = defaultdict(lambda: -1)  # packet id of packets we send - other end's receive id

        self.send_buffer = Queue()
        self.running = False
        self.send_thread = Thread(target=(self._sendloop_frag if self.frag else self._sendloop_nofrag), daemon=True)

        self.is_open = False

    @property
    def addr(self):
        return self.ip, self.port

    @property
    def addr_str(self):
        return f'{self.ip}:{self.port}'

    @classmethod
    def decompile(self, data: bytes):
        # this is probably *faster* than split - just breaks into 4 pieces by first 3 \n
        ncount = 0
        indices = []
        index = -1
        for char in data:
            index += 1
            if char != ord(b'\n'):
                continue
            ncount += 1
            indices.append(index)
            if ncount == 4:
                break

        uuid = data[:indices[0]].decode()
        pid = data[indices[0]+1:indices[1]].decode()
        type_ = data[indices[1]+1:indices[2]].decode()
        frag = data[indices[2]+1:indices[3]].decode()
        data = data[indices[3]+1:]

        #print(uuid, pid, type_, frag)
        return uuid, int(pid), type_, tuple(map(int, frag.split())), data

    def compile(self, datatype: str, data: bytes, override_uuid=None, frag_num=0, frag_final=0):
        # datatype should be INFO, AUDIO, VIDEO, other
        # META is for manager to handle
        if self.frag:
            return '\n'.join((override_uuid or self.uuid, str(self.packet_id_send[datatype]), datatype, f'{frag_num} {frag_final}')).encode() + b'\n' + data
        return '\n'.join((override_uuid or self.uuid, str(self.packet_id_send[datatype]), datatype, '0 0')).encode() + b'\n' + data

    def verify_pid(self, pid, datatype):
        return pid > self.packet_id_recv[datatype]

    def send_tcp(self, datatype: str, data: bytes=b'', ignore_pid=False):
        self.tcp_send_buffer.put((datatype, data, None, 0, 0, ignore_pid))

    def _send_tcp(self, datatype: str, data: bytes=b'', send_as=None, frag_num=0, frag_final=0, ignore_pid=False):
        if not ignore_pid:
            self.packet_id_send[datatype] += 1
        cmp = self.compile(datatype, data, override_uuid=send_as, frag_num=frag_num, frag_final=frag_final)
        #print('sending ', cmp)
        l = struct.pack('!H', len(cmp))
        #print(f'TCP sent ({len(cmp)}): {cmp}')
        return self.tcp_socket.sendall(l+cmp)
    def _send_all_tcp(self):
        try:
            while self.running:
                self._send_tcp(*self.tcp_send_buffer.get())
        except (ConnectionError, AttributeError) as e:
            if self.is_open:
                print('TCP sending with %s broke' % self.addr_str, str(e))
            self.tcp_socket = None

    def _recv_tcp(self):
        self._handle_tcp(data := self.tcp_socket.recv(self.manager.BUFFER))
        return data
    def _handle_tcp(self, data):
        if not data:
            return
        l = struct.unpack('!H', data[:2])[0]
        #print(f'TCP recv ({l}): {data[2:l+2]}')
        self.manager.recv_queue.put((data[2:l+2], (self.ip, self.port)))
        if len(data[2:]) > l:
            self._handle_tcp(data[l+2:])
    def _recv_all_tcp(self):
        try:
            while self.running:
                self._recv_tcp()
        except (ConnectionError, AttributeError) as e:
            if self.is_open:
                print('TCP reception with %s broke' % self.addr_str, str(e))
            self.tcp_socket = None
        except struct.error as e:
            print('TCP reception broke on unpack:', str(e))

    def reset_tcp(self):
        self.tcp_recv_thread = Thread(target=self._recv_all_tcp, daemon=True)
        self.tcp_send_thread = Thread(target=self._send_all_tcp, daemon=True)

    def _send(self, datatype: str, data: bytes=b'', send_as=None, frag_num=0, frag_final=0, ignore_pid=False):
        if not ignore_pid:
            self.packet_id_send[datatype] += 1
        self.manager.socket.sendto(self.compile(datatype, data, override_uuid=send_as, frag_num=frag_num, frag_final=frag_final), self.addr)

    # BUFFERED STUFF
    def send(self, datatype: str, data: bytes=b'', send_as=None):
        self.send_buffer.put((datatype, data, send_as))

    def start_threads(self, tcp_only=False):
        self.running = True
        if not tcp_only:
            self.send_thread.start()
        if self.tcp_socket is not None:
            self.tcp_recv_thread.start()
            self.tcp_send_thread.start()

    def close(self):
        self.running = False

    def _sendloop_nofrag(self):
        try:
            while self.running:
                self._send(*self.send_buffer.get())
        except OSError:
            print('Socket disconnected suddenly.')
    def _sendloop_frag(self):
        # 0 - reason
        # 1 - data
        # 2 - uuid
        try:
            while self.running:
                data = self.send_buffer.get()
                self.packet_id_send[data[0]] += 1

                if FRAG_LIMIT >= len(data[1]):
                    self._send(*data, ignore_pid=True)
                    continue

                for num, i in enumerate(range(0, len(data[1]), FRAG_LIMIT)):
                    self._send(
                        data[0],
                        data[1][i:min(i+FRAG_LIMIT, len(data[1]))],
                        data[2],
                        frag_num=num+1,
                        frag_final=1 if i+FRAG_LIMIT >= len(data[1]) else 0,
                        ignore_pid=True
                    )

        except OSError:
            print('Socket disconnected suddenly.')


def iterq(queue: Queue):
    """Creates an iterator over a Queue object"""
    while not queue.empty():
        yield queue.get()
