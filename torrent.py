from thread import start_new_thread
import lightdht
import struct
import time

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
				

	def run(self):

		self.log("Getting peer list...")
		peer_list = None
		tries = 0
		while peer_list == None:
			try:
				peer_list = self.dht.get_peers(self.info_hash)
			except RuntimeError:
				if tries >= 3:
					break

				self.log("Problem getting peer list")
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
			self.loadFromPeer(ip, port)					
	
	def log(self, what):
		print "Torrent "+(self.info_hash.encode("hex"))+": "+str(what)
