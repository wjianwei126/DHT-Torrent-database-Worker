from thread import start_new_thread
import lightdht
import struct
import time
import socket

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


class Peer:

	def _init__(self, torrent, ip, port):
		self.torrent = torrent
		self.ip = ip
		self.port = port
		self._openConnection()

	def _openConnection(self):
		self.socket = socket.create_connection(ip, port)
		#Perform the handshake
		#           1 byte         8 byte      20byte     20byte
		#handshake: <pstrlen><pstr><reserved><info_hash><peer_id>
		structstr = ">Bssss"
		pstr = "BitTorrent protocol"
		pstr_len = len(pstr)
		reserved = ''.join(chr(random.randint(0,255)) for _ in range(8))
		info_hash = self.torrent.info_hash
		_id = self.torrent.dht._id
		packed = struct.pack(structstr,pstr_len,pstr,reserved,info_hash,_id)
		self.socket.send(packed)
		self._receiveHandshake(socket)
	
	def _receiveHandshake(self, socket):
		pstr_len = struct.unpack(">B",socket.recv(1))
		pstr = socket.recv(pstr_len)
		if pstr != "BitTorrent protocol":
			socket.close()
			raise PeerException, "Peer uses wrong protocol: ", pstr
		reserved = socket.recv(8)
		info_hash = socket.recv(20)
		if info_hash != self.torrent.info_hash:
			socket.close()
			raise PeerException, "Peer serves wrong torrent: ", info_hash
		peer_id = socket.recv(20)
		self.torrent.log("Connected to peer: "+peer_id.encode("hex"))
		self.socket = socket

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

	def receiveMetadata(self):
		while True:
			length, msgtype, content = self._receiveMessage()
			if length > 0:
				if msgtype == 20:
					#extended
					self._extended(content)
				elif msgtype == 0:
					#Choke
				elif msgtype == 1:
					#unchoke
				elif msgtype == 2:
					#interested
				elif msgtype == 3:
					#not interested
				elif msgtype == 4:
					#have

	def _extended(self, data):
		msgtype = struct.unpack(">B", data[0])
		if msgtype == 0:
			#handshake

class Torrent:
	
	def __init__(self, dht, info_hash):
		self.dht = dht
		self.info_hash = info_hash
		self.metadata = []
		self.metadataLength = -1
		start_new_thread(self.run, tuple())
		
	def loadFromPeer(self, ip, port):
		ips = intToIp(ip)
		self.log("Connecting to peer "+ips+":"+str(port))
		peer = Peer(self, ips, port)					

	def run(self):

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
			self.log("Couldn't get peer list, exiting...")
			return

		self.log("Got "+str(len(peer_list))+" peers")
		if len(peer_list) == 0:
			self.log("Not enough peers, exiting...")
		
		for peer in peer_list:
			data = struct.unpack('>LH',peer)
			ip = data[0]
			port = data[1]
			try:
				self.loadFromPeer(ip, port)					
			except Exception, e:
				self.log("Exception while loading metadata from peer: "+str(e))

	def log(self, what):
		print "Torrent "+(self.info_hash.encode("hex"))+": "+str(what)
