import re
import json

r_yt_initial_data = re.compile(r"""^(?:\s*window\["ytInitialData"\]|var ytInitialData) = (\{.*\});\s*\n?$""", re.M)

def extract_yt_initial_data(content):
	m_yt_initial_data = re.search(r_yt_initial_data, content)
	if m_yt_initial_data:
		yt_initial_data = json.loads(m_yt_initial_data.group(1))
		return yt_initial_data
	else:
		raise Exception("Could not match ytInitialData in content")
