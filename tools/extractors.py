import re
import json
from functools import reduce

r_yt_initial_data = re.compile(r"""(?:^\s*window\["ytInitialData"\]|var ytInitialData) = (\{.+?\});(?:\s*$|</script>)""", re.S + re.M)
r_yt_initial_player_response = re.compile(r"""(?:^\s*window\["ytInitialPlayerResponse"\]|var ytInitialPlayerResponse) = (\{.+?\});(?:\s*$|</script>|var )""", re.S + re.M)
r_yt_cfg = re.compile(r"""ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;""")

def extract_yt_initial_data(content):
	m_yt_initial_data = re.search(r_yt_initial_data, content)
	if m_yt_initial_data:
		yt_initial_data = json.loads(m_yt_initial_data.group(1))
		return yt_initial_data
	else:
		raise Exception("Could not match ytInitialData in content")

def extract_yt_initial_player_response(content):
	m_yt_initial_player_response = re.search(r_yt_initial_player_response, content)
	if m_yt_initial_player_response:
		yt_initial_player_response = json.loads(m_yt_initial_player_response.group(1))
		return yt_initial_player_response
	else:
		raise Exception("Could not match ytInitialPlayerResponse in content")

def extract_yt_cfg(content):
	m_yt_cfg = re.search(r_yt_cfg, content)
	if m_yt_cfg:
		return json.loads(m_yt_cfg.group(1))
	raise Exception("Could not match ytcfg in content")

def eu_consent_cookie():
	return {"SOCS": "CAI"}

def is_in(o, key):
	if isinstance(o, list):
		return type(key) == int and key >= 0 and key < len(o)
	else:
		return key in o

def deep_get(o, properties):
	return reduce(lambda a, b: a and is_in(a, b) and a[b] or None, [o, *properties])
