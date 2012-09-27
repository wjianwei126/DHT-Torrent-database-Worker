from thread import start_new_thread
import lightdht
import struct
import time
import socket
import bencode

def intToIp( intip ):
	octet = ''
	for exp in [3,2,1,0]:
		octet = octet + str(intip / ( 256 ** exp )) + "."
		intip = intip % ( 256 ** exp )
	return(octet.rstrip('.'))
	 
def ipToInt( dotted_ip ):
	exp = 3
	intip = 0
	for quad in dotted_ip.split('.'):
		intip = intip + (int(quad) * (256 ** exp))
		exp = exp - 1
	return(intip)

class PeerException(Exception):
	pass

class Peer:
	def __init__(self, socket, torrent = None):
		self.socket = socket
		self.torrent = torrent
		self.handshakeSend = False
		self.handshakeReceived = False
		
	def _receiveHandshake(self):
		pstr_len = struct.unpack(">B",self.socket.recv(1))
		self.pstr = self.socket.recv(pstr_len) 
		if pstr != "BitTorrent protocol":
			socket.close()
			raise PeerException, "Peer uses wrong protocol (", pstr
		
		self.reserved = self.socket.recv(8)
		#Check if the peer supports the extension protocol
		if reserved & 0x10 != 0x10:
			self.socket.close()
			raise PeerException, "Peer does not support the extension protocol"

		self.info_hash = self.socket.recv(20)
		self.peer_id = self.socket.recv(20)
		self.handshakeReceived = True

	def _sendMessage(self, msgtype, contents):
		pass

	#Returns tuple(length, msgtype, data)
	def _receiveMessage(self):
		socket = self.socket
		length = struct.unpack(">I",socket.recv(4))
		masgtype = None
		content = None
		if length>0:
			msgtype = struct.unpack(">B",socket.recv(1))
			if length>1:
				content = socket.recv(length-1)

		return (length, msgtype, content)
	
	def _sendHandshake(self):
		#Send the handshake
		#           1 byte         8 byte      20byte     20byte
		#handshake: <pstrlen><pstr><reserved><info_hash><peer_id>
		structstr = ">Bssss"
		pstr = "BitTorrent protocol"
		pstr_len = len(pstr)
		reserved = [chr(0) for i in range(8)]
		reserved[5] = chr(0x10)
		reserved = ''.join(reserved)
		info_hash = self.torrent.info_hash
		_id = "-TI0001-TORRENTINDEX"
		packed = struct.pack(structstr,pstr_len,pstr,reserved,info_hash,_id)
		self.socket.send(packed)
		self.handshakeSend = True
	
	def doReceiveHandshake(self):
		if not self.handshakeReceived:
			self._receiveHandshake()

	def performHandshake(self):
		"""
		Performs a complete handshake with the peer
		"""
		while not self.handshakeSend or not self.handshakeReceived:
			if not self.handshakeSend and self.torrent != None:
				self._sendHandshake()
			if not self.handshakeReceived:
				self._receiveHandshake()

	#Mainloop
	def loop(self):
		while True:
			length, msgtype, content = self._receiveMessage()
			if length > 0:
				if msgtype == 20:
					#extended
					self._extended(content)
				elif msgtype == 0:
					#Choke
					pass
				elif msgtype == 1:
					#unchoke
					pass
				elif msgtype == 2:
					#interested
					pass
				elif msgtype == 3:
					#not interested
					pass
				elif msgtype == 4:
					#have
					pass

	def _extended(self, data):
		msgtype = struct.unpack(">B", data[0])
		if msgtype == 0:
			#handshake
			payload = bencode.bdecode(data)
			print "GOT HANDSHAKE: "+payload

	def close(self):
		self.socket.close()

class Torrent:
	def __init__(self, dht, info_hash):
		self.dht = dht
		self.info_hash = info_hash
		self.metadata = []
		self.metadataLength = -1
		self.finished = False
		self.peer_list = set()
		self.peers = []
		start_new_thread(self._run, tuple())
		
	def openConnection(self, ip, port):
		self.log("Connecting to peer "+ip+":"+str(port))
		socket = socket.create_connection((ip, port),20)
		peer = Peer(self, socket)
		peer.performHandshake()
		self._handlePeer(peer)

	def addPeer(self, peer):
		peer.torrent = self
		peer.performHandshake()
		self._handlePeer(peer)

	def _handlePeer(self, peer):
		if peer.info_hash != self.info_hash:
			peer.close()
			raise PeerException, "Peer is serving the wrong torrent"
		self.peers.append(peer)
		
		try:
			peer.loop()
			peer.close()
		finally:
			self.peers.remove(peer)
	
	def _updatePeers(self):
		self.log("Getting peer list...")
		peer_list = None
		tries = 0
		while peer_list == None:
			try:
				peer_list = self.dht.get_peers(self.info_hash)
			except Exception, e:
				if tries >= 3:
					break
				self.log("Problem getting peer list: "+str(e))
				tries = tries + 1
				time.sleep(10)

		if peer_list == None:
			self.log("Couldn't get peer list...")
			return
		self.peer_list = set(self.peer_list + peer_list)
		self.log("Have "+str(len(self.peer_list))+" peers")

	def _run(self):
		if len(peer_list) == 0:
			self.log("Not enough peers, exiting...")
		
		for peer in peer_list:
			data = struct.unpack('<IH',peer)
			ip = data[0]
			port = data[1]
			ips = intToIp(ip)
			try:
				self.openConnection(ips, port)					
			except Exception, e:
				self.log("Error while loading metadata from peer "+ips+": "+str(e))

	def log(self, what):
		print "Torrent "+(self.info_hash.encode("hex"))+": "+str(what)

class TorrentManager:
	def __init__(self, dht, port, onfinish):
		self.dht = dht
		self.port = port
		self.onfinish = onfinish
		self.running = {}
		start_new_thread(self._run,tuple())

	def addTorrent(self, info_hash):
		if not info_hash in self.running:
			torrent = Torrent(self.dht, info_hash)
			self.running.append(torrent)

	def fetchAndRemove(self):
		pass

	def _run(self):
		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.bind((socket.gethostname(), self.port))
		serversocket.listen(10)
		while True:
			socket, address = serversocket.accept()
			start_new_thread(self._handlePeer, tuple(socket))

	def _handlePeer(self, socket):
		peer = Peer(None, socket)
		peer.doReceiveHandshake()
		info_hash = peer.info_hash			
		if info_hash in self.running:
			torrent = self.running[info_hash]
			torrent.addPeer(peer)
		else:
			peer.close()
