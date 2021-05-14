import re
import json
import random

r_yt_initial_data = re.compile(r"""(?:^\s*window\["ytInitialData"\]|var ytInitialData) = (\{.+?\});(?:\s*$|</script>)""", re.S + re.M)
r_yt_initial_player_response = re.compile(r"""(?:^\s*window\["ytInitialPlayerResponse"\]|var ytInitialPlayerResponse) = (\{.+?\});(?:\s*$|</script>|var )""", re.S + re.M)

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

def eu_consent_cookie():
	return {"CONSENT": "YES+cb.20210509-17-p0.en+F+{}".format(random.randint(100, 999))}
