import logging
import hashlib
import time
import os
import lightdht
import torrent

# Enable logging:
lightdht.logger.setLevel(logging.WARNING)	 
formatter = logging.Formatter("[%(levelname)s@%(created)s] %(message)s")
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(formatter)
lightdht.logger.addHandler(stdout_handler)

# Create a DHT node.
id_ = os.urandom(20) #hashlib.sha1("Change this to avoid getting ID clashes").digest()
dht = lightdht.DHT(port=8000, id_=id_) 

#Running torrents that are downloading metadata
manager = torrent.TorrentManager(dht, 8000, None)

# handler
def myhandler(rec, c):
	try:
		if "a" in rec:
			a = rec["a"]
			if "info_hash" in a:
				info_hash = a["info_hash"]
				manager.addTorrent(info_hash)

	finally:
		# always ALWAYS pass it off to the real handler
		dht.default_handler(rec,c) 

dht.handler = myhandler
dht.active_discovery = True 
dht.self_find_delay = 30

test_hash = "8ac3731ad4b039c05393b5404afa6e7397810b41".decode("hex")
manager.addTorrent(test_hash)

# Start it!
with dht:
	# Go to sleep and let the DHT service requests.
	while True:
		time.sleep(1)
