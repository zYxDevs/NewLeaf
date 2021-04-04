import configuration
import datetime
import re
import time
from urllib.parse import urlparse, urlencode, parse_qs

def length_text_to_seconds(text):
	s = text.split(":")
	return sum([int(x) * 60**(len(s)-i-1) for i, x in enumerate(s)])

def combine_runs(runs):
	if "simpleText" in runs: # check if simpletext instead
		return runs["simpleText"]
	if "runs" in runs: # check if already unpacked
		runs = runs["runs"]
	return "".join([r["text"] for r in runs])

def escape_html_textcontent(text):
	return (
		text
			.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
			.replace('"', "&quot;")
			.replace("\n", "<br>")
	)

def combine_runs_html(runs):
	if "runs" in runs: # check if already unpackged
		runs = runs["runs"]
	result = ""
	for part in runs:
		if part.get("bold"):
			result += "<b>{}</b>".format(escape_html_textcontent(part["text"]))
		else:
			result += part["text"]
	return result

def add_html_links(text):
	r_link = re.compile(r"""https?://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:/[^\s,<>)]*)?""") # it's okay, I guess.
	match = r_link.search(text)
	if match is not None:
		link = match.group()
		text = text[:match.start()] + '<a href="{}">{}</a>'.format(link, link) + add_html_links(text[match.end():])
	return text

def view_count_text_to_number(text):
	if text is None:
		return 0

	first_word = text.split(" ")[0].replace(",", "")
	if first_word == "No":
		return 0
	else:
		return int(first_word)

def get_view_count_or_recommended(view_count_container):
	if "viewCountText" in view_count_container:
		text = view_count_container["viewCountText"]
	elif "viewCount" in view_count_container:
		text = view_count_container["viewCount"]
	else:
		return 0

	if "runs" in text: # has live viewers
		return view_count_text_to_number(combine_runs(text))
	else:
		text = text["simpleText"]
		if text == "Recommended for you":
			return 0 # subject to change?
		else:
			return view_count_text_to_number(text)

def get_view_count_text_or_recommended(view_count_container):
	if "viewCountText" in view_count_container:
		text = view_count_container["viewCountText"]
	elif "viewCount" in view_count_container:
		text = view_count_container["viewCount"]
	else:
		return None

	if "runs" in text: # has live viewers
		return combine_runs(text)
	else: # has past views
		text = text["simpleText"]
		if text == "Recommended for you":
			return "Recommended for you" #subject to change?
		else:
			return text

def is_live(length_container):
	return "lengthText" not in length_container

def get_length_or_live_now(length_container):
	if "lengthText" in length_container:
		return length_text_to_seconds(length_container["lengthText"]["simpleText"])
	else:
		return -1

def get_length_text_or_live_now(length_container):
	if "lengthText" in length_container:
		return length_container["lengthText"]["simpleText"]
	else:
		return "LIVE"

def generate_video_thumbnails(id):
	types = [
		# quality, url part, width, height
		["maxres", "maxresdefault", 1280, 720],
		["maxresdefault", "maxresdefault", 180, 720],
		["sddefault", "sddefault", 640, 480],
		["high", "hqdefault", 480, 360],
		["medium", "mqdefault", 320, 180],
		["default", "default", 120, 90],
		["start", "1", 120, 90],
		["middle", "2", 120, 90],
		["end", "3", 120, 90]
	]
	return [{
		"quality": type[0],
		"url": "{}/vi/{}/{}.jpg".format(configuration.website_origin, id, type[1]),
		"second__originalUrl": "https://i.ytimg.com/vi/{}/{}.jpg".format(id, type[1]),
		"width": type[2],
		"height": type[3]
	} for type in types]

def generate_full_author_thumbnails(original):
	r_size_part = re.compile(r"""=s[0-9]+-""")
	match = r_size_part.search(original[0]["url"])
	if match:
		template = re.sub(r_size_part, "=s{}-", original[0]["url"])
		sizes = [32, 48, 76, 100, 176, 512]
		return [{
			"url": template.format(size),
			"width": size,
			"height": size
		} for size in sizes]
	else:
		return original

def normalise_url_protocol(url):
	if url.startswith("//"):
		url = "https:" + url
	return url

def uncompress_counter(text):
	if text.lower() == "no" or text.lower() == "unknown":
		return 0
	last = text[-1:].lower()
	if last >= "0" and last <= "9":
		return int(last)
	else:
		multiplier = 1
		if last == "k":
			multiplier = 1000
		elif last == "m":
			multiplier = 1000000
		elif last == "b":
			multiplier = 1000000000
		return int(float(text[:-1]) * multiplier)

def past_text_to_time(text):
	words = text.split(" ")
	if words[0] == "Streamed":
		words = words[1:]
	if len(words) != 3:
		print(words)
		raise Exception("Past text is not 3 words")
	if words[2] != "ago":
		print(words)
		raise Exception('Past text does not end with "ago"')
	number = int(words[0])
	unit = words[1][:2]
	multiplier = 1
	if unit == "se":
		multiplier = 1
	elif unit == "mi":
		multiplier = 60
	elif unit == "ho":
		multiplier = 60 * 60
	elif unit == "da":
		multiplier = 24 * 60 * 60
	elif unit == "we":
		multiplier = 7 * 24 * 60 * 60
	elif unit == "mo":
		multiplier = 30 * 24 * 60 * 60
	elif unit == "ye":
		multiplier = 365 * 24 * 60 * 60
	return int(datetime.datetime.now().timestamp()) - number * multiplier

def time_to_past_text(timestamp):
	now = int(time.time())
	diff = now - timestamp
	units = [
		["year", 365 * 24 * 60 * 60],
		["month", 30 * 24 * 60 * 60],
		["week", 7 * 24 * 60 * 60],
		["day", 24 * 60 * 60],
		["hour", 60 * 60],
		["minute", 60],
		["second", 1]
	]
	for index in range(len(units)):
		unit_name, unit_value = units[index]
		if diff > unit_value or index + 1 >= len(units):
			number = diff // unit_value
			plural_unit = unit_name if number == 1 else unit_name + "s"
			return "{} {} ago".format(number, plural_unit)

def get_language_label_from_url(url_string):
	url = urlparse(url_string)
	params = parse_qs(url.query)
	label = params["name"][0] if "name" in params else "" # name may be in params with empty value
	return label

def get_subtitle_api_url(id, label, language_code):
	subtitle_api_url = "/api/v1/captions/{}?".format(id)
	params = {}

	if label and "auto-generated" in label:
		params["label"] = label
	else:
		params["lang"] = language_code

	return subtitle_api_url + urlencode(params)
