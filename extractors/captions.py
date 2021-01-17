import requests
from extractors.video import extract_video
from tools.converters import escape_html_textcontent, get_subtitle_api_url
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

def extract_captions(id, **kwargs):
	captions = extract_captions_from_api(id)
	return extract_captions_from_dict(captions, **kwargs)

# Return captions for the language specified,
# The captions list otherwise
def extract_captions_from_dict(captions, **kwargs):
	lang = None
	label = None

	if "lang" in kwargs:
		lang = kwargs["lang"]
	elif "label" in kwargs:
		label = kwargs["label"]
	else:
		return captions

	for subtitle in captions["captions"]:
		if lang == subtitle["languageCode"] or label == subtitle["label"]:
			url = subtitle["second__subtitleUrl"]

			with requests.get(url) as r:
				r.raise_for_status()
				return r.content.decode("utf8")

# Currently unused in favour of extract_captions_from_api.
def extract_captions_from_video(id):
	return {
		"captions": extract_video(id)["captions"]
	}

# no automatic captions
def extract_captions_from_api(id):
	url = "https://video.google.com/timedtext?hl=en&type=list&v=%s" % id
	with requests.get(url) as r:
		r.raise_for_status()

		transcript = ET.fromstring(r.content.decode("utf8"))
		tracks = transcript.findall("track")

		captions = []
		result = {
			"captions": captions
		}

		for track in tracks:
			language_code = track.attrib["lang_code"]
			label = track.get("name", default=language_code)
			subtitle_api_url = get_subtitle_api_url(id, label, language_code)

			params = urlencode({
				"lang": language_code,
				"v": id,
				"fmt": "vtt",
				"name": label
			})

			subtitle_url = "https://www.youtube.com/api/timedtext?" + params

			captions.append({
				"label": label if label != "" else language_code,
				"languageCode": language_code,
				"url": subtitle_api_url,
				"second__subtitleUrl": subtitle_url
			})

		return result
