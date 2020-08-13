import requests
from cachetools import TTLCache

suggestions_cache = TTLCache(maxsize=400, ttl=60)

def extract_search_suggestions(q):
	if q in suggestions_cache:
		return suggestions_cache[q]

	params = {
		"client": "youtube",
		"hl": "en",
		"gl": "us",
		"gs_rn": "64",
		"gs_ri": "youtube",
		"ds": "yt",
		"cp": "3",
		"gs_id": "k",
		"q": q,
		"xhr": "t",
		# "xssi": "t"
	}
	with requests.get("https://clients1.google.com/complete/search", params=params) as r:
		r.raise_for_status()
		response = r.json()
		result = {
			"query": q,
			"suggestions": [s[0] for s in response[1]]
		}
		suggestions_cache[q] = result
		return result
