import bencode

print str(bencode.bdecode(open("torrent").read()))
