# This file is placed into the Public Domain

"""
Bitcoin address validator by Gavin Andresen.
https://bitcointalk.org/index.php?topic=1026.0;all

Gratipay changes:

 [x] Removed Django field
 [x] Replaced pycrypto with hashlib
 [x] Added self-test with remote Bitcoin dataset
 [x] Added cmdline interface for checking address
       utils.bitcoin.py -i [hash]

"""

from hashlib import sha256

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
  """ encode v, which is a string of bytes, to base58.
  """

  long_value = 0L
  for (i, c) in enumerate(v[::-1]):
    long_value += (256**i) * ord(c)

  result = ''
  while long_value >= __b58base:
    div, mod = divmod(long_value, __b58base)
    result = __b58chars[mod] + result
    long_value = div
  result = __b58chars[long_value] + result

  # Bitcoin does a little leading-zero-compression:
  # leading 0-bytes in the input become leading-1s
  nPad = 0
  for c in v:
    if c == '\0': nPad += 1
    else: break

  return (__b58chars[0]*nPad) + result

def b58decode(v, length):
  """ decode v into a string of len bytes
  """
  long_value = 0L
  for (i, c) in enumerate(v[::-1]):
    long_value += __b58chars.find(c) * (__b58base**i)

  result = ''
  while long_value >= 256:
    div, mod = divmod(long_value, 256)
    result = chr(mod) + result
    long_value = div
  result = chr(long_value) + result

  nPad = 0
  for c in v:
    if c == __b58chars[0]: nPad += 1
    else: break

  result = chr(0)*nPad + result
  if length is not None and len(result) != length:
    return None

  return result

def get_bcaddress_version(strAddress):
  """ Returns None if strAddress is invalid.  Otherwise returns integer version of address. """
  addr = b58decode(strAddress,25)
  if addr is None: return None
  version = addr[0]
  checksum = addr[-4:]
  vh160 = addr[:-4] # Version plus hash160 is what is checksummed
  h3=sha256(sha256(vh160).digest()).digest()
  if h3[0:4] == checksum:
    return ord(version)
  return None

def validate(address):
  if get_bcaddress_version(address) == None:
    return False
  else:
    return True

if __name__ == '__main__':
  print("running self-tests.. (use -i [hash] for cmdline address check)")
  import sys
  if "-i" in sys.argv:
    print sys.argv
    if len(sys.argv) > 2:
      addr = sys.argv[-1]
    else:
      addr = raw_input("Enter address: ")
    if validate(addr):
      print "ok."
      sys.exit(0)
    else:
      print "invalid."
      sys.exit(-1)

  import urllib, json
  ok = True
  print("..fetching dataset of invalid hashes")
  invalid = "https://raw.githubusercontent.com/bitcoin/bitcoin/master/src/test/data/base58_keys_invalid.json"
  for entry in json.loads(urllib.urlopen(invalid).read()):
    if validate(entry[0]):
      print entry[0], "- should be invalid - check failed"
      ok = False

  print("fetching dataset of valid hashes..")
  valid = "https://raw.githubusercontent.com/bitcoin/bitcoin/master/src/test/data/base58_keys_valid.json"
  for entry in json.loads(urllib.urlopen(valid).read()):
    if not validate(entry[0]):
      privkey = entry[2][u'isPrivkey']
      # validation fails for private key (https://en.bitcoin.it/wiki/Private_key)
      if not privkey:
        print entry[0], "- should be valid - check failed"
        ok = False

  sys.exit('some tests failed.') if ok else sys.exit('some tests failed.')
