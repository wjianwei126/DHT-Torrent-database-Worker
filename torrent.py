from thread import start_new_thread
import lightdht
import struct
import time
import socket as pysocket
import bencode
import traceback
import math
import random
import hashlib

def recvAll(stream, l):
	data = ""
	start = time.time()
	while len(data) < l:
		if time.time() > start + 60:
			raise PeerException, "Read timed out"
		data = data + stream.recv(l - len(data))
	return data

class PeerException(Exception):
	pass

class Peer:
	def __init__(self, socket, torrent = None):
		self.socket = socket
		self.torrent = torrent
		self.handshakeSend = False
		self.handshakeReceived = False
		self.extensionHandshakeReceived = False
		self.closed = False

	def _receiveHandshake(self):
		pstr_len = ord(recvAll(self.socket,1))
		self.pstr = recvAll(self.socket, pstr_len) 
		if self.pstr != "BitTorrent protocol":
			socket.close()
			raise PeerException, "Peer uses wrong protocol (", pstr
		
		self.reserved = recvAll(self.socket,8)
		#Check if the peer supports the extension protocol
		if ord(self.reserved[5]) & 0x10 != 0x10:
			self.socket.close()
			raise PeerException, "Peer does not support the extension protocol"

		self.info_hash = recvAll(self.socket,20)
		self.peer_id = recvAll(self.socket,20)
		self.handshakeReceived = True

	def _sendMessage(self, msgtype = None, contents = None):
		l = 0
		msg = ""
		if msgtype != None:
			l = l + 1
			msg = msg + chr(msgtype)
		if contents != None:
			l = l + len(contents)
			msg = msg + contents
		packed = struct.pack(">I",l) + msg
		self.socket.sendall(packed)

	#Returns tuple(length, msgtype, data)
	def _receiveMessage(self):
		socket = self.socket
		length = struct.unpack(">I",recvAll(socket,4))[0]
		masgtype = None
		content = None
		if length>0:
			msgtype = ord(recvAll(socket,1))
			if length>1:
				content = recvAll(socket,length-1)

		return (length, msgtype, content)
	
	def _sendHandshake(self):
		#Send the handshake
		#           1 byte         8 byte      20byte     20byte
		#handshake: <pstrlen><pstr><reserved><info_hash><peer_id>
		pstr = "BitTorrent protocol"
		pstr_len = len(pstr)
		reserved = [chr(0) for i in range(8)]
		reserved[5] = chr(0x10)
		reserved = ''.join(reserved)
		info_hash = self.torrent.info_hash
		_id = "-TI0001-TORRENTINDEX"
		packed = chr(pstr_len) + pstr + reserved + info_hash + _id
		self.socket.sendall(packed)
		self._sendExtensionHandshake()
		self.handshakeSend = True

	def _sendExtensionHandshake(self):
		contents = {'m': {'ut_metadata': 3}, 'metadata_size':0,'v':'DHT-Crawler-0.1'}	
		self._sendExtensionMessage(0, contents)		
	
	def _sendExtensionMessage(self, msg, contents, add = None):
		data = chr(msg) + bencode.bencode(contents) 
		if add != None:
			data = data + add		
		self._sendMessage(20, data)

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
	

	def _requestPiece(self):
		if self.torrent.finished:
			return
		piece = self.torrent.getNeededPiece()
		self._sendExtensionMessage(self.metadata_id,{'msg_type':0,'piece':piece})		

	#Mainloop
	def loop(self):
		while not self.torrent.finished and not self.closed:
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
	
	def _metadataExt(self, msg, extra):
		msg_type = msg['msg_type']
		torrent = self.torrent
		if msg_type == 0:
			#request
			#currently we are receting all of them
			piece = msg['piece']
			self.sendExtensionMessage(self.metadata_id,{'msg_type':2,'piece':piece})				
		elif msg_type == 1:
			#data
			piece = msg['piece']	
			self.torrent.gotMetadata(piece, extra)	
			self._requestPiece()
		elif msg_type == 2:
			#reject
			self.socket.close()
			raise PeerException, "Peer is rejecting metadata requests"

	def _extended(self, data):
		msgtype = ord(data[0])
		if msgtype == 0 and not self.extensionHandshakeReceived:
			#handshake
			payload = bencode.bdecode(data[1:])
			if not "metadata_size" in payload or not "ut_metadata" in payload['m']:
				self.socket.close()
				raise PeerException, "Peer does not support the ut_metadata extension"
			
			size = payload['metadata_size']
			if size == 0:
				self.socket.close()
				raise PeerException, "The peer does not appear to have any metadata"

			self.torrent.setMetadataSize(size)
			self.metadata_id = payload['m']['ut_metadata']
			self.extensionHandshakeReceived = True
			#everything seems fine, go ahead an request the first bit of metadata
			self._requestPiece()
		elif not self.extensionHandshakeReceived:
			self.socket.close()
			raise PeerException, "Peer send extension messages before handshake"
		
		if msgtype == 3:
			#Got metadata extension message
			r, l = bencode.bdecode_len(data[1:])
			self._metadataExt(r, data[l+1:])

	def close(self):
		self.socket.close()
		self.closed = True

class Torrent:
	def __init__(self, dht, info_hash):
		self.dht = dht
		self.info_hash = info_hash
		self.metadata = {}
		self.metadataSize = -1
		self.metadataPieces = 0
		self.finished = False
		self.peer_list = set()
		self.peers = []
		start_new_thread(self._run, tuple())
	
	def gotMetadata(self, piece, content):
		if not piece in self.metadata:
			self.metadata[piece] = content
			self.log("Got metadata "+str(piece+1)+"/"+str(self.metadataPieces))
		#Check if the torrent is finished
		if self.getNeededPiece() == -1:
			self.finished = True

	def disconnect(self):
		try:
			for peer in self.peers:
				peer.close()
		except Exception, e:
			traceback.print_exc()	

	def setMetadataSize(self, size):
		self.metadataSize = size
		self.metadataPieces = math.ceil(size / 16384)		
		self.log("Downloading "+str(self.metadataPieces)+" pieces of metadata")
	
	def getNeededPiece(self):
		piece = 0
		pieces = []
		while piece < self.metadataPieces:
			if not piece in self.metadata:
				pieces.append(piece)
			piece = piece + 1
		if len(pieces) == 0:
			return -1
		return random.choice(pieces)

	def openConnection(self, ip, port):
		self.log("Connecting to peer "+ip+":"+str(port))
		socket = pysocket.create_connection((ip, port),20)
		peer = Peer(socket, self)
		peer.performHandshake()
		self._handlePeer(peer)

	def addPeer(self, peer):
		peer.torrent = self
		peer.performHandshake()
		self._handlePeer(peer)

	def _handlePeer(self, peer):
		self.log("Trying to download metadata from peer")
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
		self.peer_list = set(list(self.peer_list) + peer_list)
		self.log("Have "+str(len(self.peer_list))+" peers")

	def _run(self):
		self._updatePeers()
		if len(self.peer_list) == 0:
			self.log("Not enough peers, exiting...")
		
		for peer in self.peer_list:
			if self.finished:
				return
			data = struct.unpack('>BBBBH',peer)
			ip = '.'.join([str(d) for d in data[:4]])
			port = data[4]
			try:
				self.openConnection(ip, port)					
			except Exception, e:
				self.log("Error while loading metadata from peer "+ip+": "+str(e))
				#traceback.print_exc()

	def prepareData(self):
		num = len(self.metadata)
		if num != self.metadataPieces or num == 0:
			return None
		data = ""
		for i in range(num):
			data = data + self.metadata[i]
		sha = hashlib.sha1()
		sha.update(data)
		info_hash = sha.digest()
		if info_hash != self.info_hash:
			self.log("The hashes do not match! ("+info_hash+") ")
			return None
		return data		

	def log(self, what):
		print "Torrent "+(self.info_hash.encode("hex"))+": "+str(what)

class TorrentManager:
	def __init__(self, dht, port, onfinish):
		self.dht = dht
		self.port = port
		self.onfinish = onfinish
		self.running = {}
		#Do not handle incoming connections
		#start_new_thread(self._run,tuple())

	def addTorrent(self, info_hash):
		if not info_hash in self.running:
			torrent = Torrent(self.dht, info_hash)
			self.running[info_hash] = torrent
	
	def fetchAndRemove(self):
		for info_hash in self.running:
			torrent = self.running[info_hash]
			if torrent.finished:
				del self.running[info_hash]
				torrent.disconnect()
				return (info_hash, torrent.prepareData())
		return None

	def _run(self):
		serversocket = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_STREAM)
		serversocket.bind(('localhost', self.port))
		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.bind((socket.gethostname(), self.port))
		serversocket.listen(10)
		while True:
			socket, address = serversocket.accept()
			start_new_thread(self._handlePeer, tuple(socket))

	def _handlePeer(self, socket):
		peer = Peer(socket)
		peer.doReceiveHandshake()
		info_hash = peer.info_hash			
		if info_hash in self.running:
			torrent = self.running[info_hash]
			torrent.addPeer(peer)
		else:
			peer.close()
