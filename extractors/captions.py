import requests
from extractors.video import extract_video
from tools.converters import escape_html_textcontent, get_subtitle_api_url
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

def extract_captions(id, **kwargs):
	if "label" in kwargs and "auto-generated" in kwargs["label"]:
		captions = extract_captions_from_video(id)
	else:
		captions = extract_captions_from_api(id)
	return extract_captions_from_dict(captions, **kwargs)

# Return captions for the language specified,
# The captions list otherwise
def extract_captions_from_dict(captions, *, lang=None, label=None):
	if lang is None and label is None:
		return captions

	url = next(caption["second__remoteUrl"] for caption in captions["captions"] if caption["languageCode"] == lang or caption["label"] == label)
	with requests.get(url) as r:
		r.raise_for_status()
		return r

# List of captions directly from youtube, but no automatic
def extract_captions_from_api(id):
	url = "https://video.google.com/timedtext?hl=en&type=list&v={}".format(id)
	with requests.get(url) as r:
		if r.status_code == 404:
			return {
				"error": "Video unavailable",
				"identifier": "NOT_FOUND"
			}

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
				"second__remoteUrl": subtitle_url
			})

		return result

# We'll fall back to this function for auto-captions.
def extract_captions_from_video(id):
	return {
		"captions": extract_video(id)["captions"]
	}
