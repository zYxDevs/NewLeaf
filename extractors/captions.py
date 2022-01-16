import re
import requests
from extractors.video import extract_video
from tools.converters import escape_html_textcontent, get_subtitle_api_url
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

def extract_captions(id, **kwargs):
	captions = extract_captions_from_video(id)
	return extract_captions_from_dict(captions, **kwargs)

# Return captions for the language specified,
# The captions list otherwise
def extract_captions_from_dict(captions, *, lang=None, label=None):
	if lang is None and label is None:
		return captions

	url = next(caption["second__remoteUrl"] for caption in captions["captions"] if caption["languageCode"] == lang or caption["label"] == label)
	r = requests.get(url)
	r.raise_for_status()
	# remove extraneous " align:start position:0%" on timestamps lines on auto-generated captions
	if (lang and "auto-generated" in lang) or (label and "auto-generated" in label):
		return re.sub(r"^([0-9:.]+ --> [0-9:.]+).*$", r"\1", r.content.decode("utf8"), flags=re.MULTILINE)
	return r

def extract_captions_from_video(id):
	return {
		"captions": extract_video(id)["captions"]
	}
