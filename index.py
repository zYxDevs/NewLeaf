import configuration
import cherrypy
import json
import youtube_dl
import datetime
import dateutil.parser
import os
import re
import json
import traceback
import requests
import xml.etree.ElementTree as ET
from cachetools import TTLCache

ytdl_opts = {
	"quiet": True,
	"dump_single_json": True,
	"playlist_items": "1-100",
	"extract_flat": "in_playlist"
}
ytdl = youtube_dl.YoutubeDL(ytdl_opts)

ytdl_save_opts = ytdl_opts.copy()
ytdl_save_opts["write_pages"] = True
ytdl_save = youtube_dl.YoutubeDL(ytdl_save_opts)

def length_text_to_seconds(text):
	s = text.split(":")
	return sum([int(x) * 60**(len(s)-i-1) for i, x in enumerate(s)])

r_yt_intial_data = re.compile(r"""^\s*window\["ytInitialData"\] = (\{.*\});\n?$""", re.M)

def extract_yt_initial_data(content):
	m_yt_initial_data = re.search(r_yt_intial_data, content)
	if m_yt_initial_data:
		yt_initial_data = json.loads(m_yt_initial_data.group(1))
		return yt_initial_data
	else:
		raise Exception("Could not match ytInitialData in content")

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
	r_link = re.compile(r"""https?://[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s,<>)]*)?""") # it's okay, I guess.
	match = r_link.search(text)
	if match is not None:
		link = match.group()
		text = text[:match.start()] + '<a href="{}">{}</a>'.format(link, link) + add_html_links(text[match.end():])
	return text

def view_count_text_to_number(text):
	return int(text.split(" ")[0].replace(",", ""))

def get_view_count_or_recommended(view_count_container):
	text = view_count_container.get("viewCountText") or view_count_container["viewCount"]
	if "runs" in text: # has live viewers
		return view_count_text_to_number(combine_runs(text))
	else:
		text = text["simpleText"]
		if text == "Recommended for you":
			return 0 # subject to change?
		else:
			return view_count_text_to_number(text)

def get_view_count_text_or_recommended(view_count_container):
	text = view_count_container.get("viewCountText") or view_count_container["viewCount"]
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
		return "Live now"

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

class Second(object):
	def __init__(self):
		self.video_cache = TTLCache(maxsize=50, ttl=300)
		self.search_cache = TTLCache(maxsize=50, ttl=300)
		self.search_suggestions_cache = TTLCache(maxsize=200, ttl=60)
		self.channel_cache = TTLCache(maxsize=50, ttl=300)

	def _cp_dispatch(self, vpath):
		if vpath[:4] == ["api", "manifest", "dash", "id"]:
			vpath[:4] = ["manifest"]
			return self

		if vpath[:2] == ["api", "v1"]:
			endpoints = [
				["channels", 1, 2],
				["videos", 1, 1],
				["search", 0, 1]
			]
			for e in endpoints:
				if vpath[2] == e[0] and len(vpath) >= e[1]+3 and len(vpath) <= e[2]+3:
					vpath[:3] = [e[0]]
					return self

		return vpath

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def videos(self, id, **kwargs):
		if id in self.video_cache:
			return self.video_cache[id]

		try:
			info = ytdl_save.extract_info(id, download=False)

			year = int(info["upload_date"][:4])
			month = int(info["upload_date"][4:6])
			day = int(info["upload_date"][6:8])
			published = int(datetime.datetime(year, month, day).timestamp())

			# Adaptive formats have either audio or video, format streams have both
			def format_is_adaptive(format):
				return format["acodec"] == "none" or format["vcodec"] == "none"

			def format_mime(format):
				sense = "video" if format["vcodec"] != "none" else "audio"
				return "{}/{}".format(sense, format["ext"])

			def format_codecs(format):
				codecs = []
				if format["vcodec"] != "none":
					codecs.append(format["vcodec"])
				if format["acodec"] != "none":
					codecs.append(format["acodec"])
				return codecs

			def format_type(format):
				return '{}; codecs="{}"'.format(format_mime(format), ", ".join(format_codecs(format)))

			result = {
				"type": "video",
				"title": info["title"],
				"videoId": info["id"],
				"videoThumbnails": generate_video_thumbnails(info["id"]),
				"storyboards": None,
				"description": info["description"],
				"descriptionHtml": add_html_links(escape_html_textcontent(info["description"])),
				"published": published,
				"publishedText": None,
				"keywords": None,
				"viewCount": info["view_count"],
				"second__viewCountText": None,
				"second__viewCountTextShort": None,
				"likeCount": info["like_count"],
				"dislikeCount": info["dislike_count"],
				"paid": None,
				"premium": None,
				"isFamilyFriendly": None,
				"allowedRegions": [],
				"genre": None,
				"genreUrl": None,
				"author": info["uploader"],
				"authorId": info["channel_id"],
				"authorUrl": info["channel_url"],
				"second__uploaderId": info["uploader_id"],
				"second__uploaderUrl": info["uploader_url"],
				"authorThumbnails": [],
				"subCountText": None,
				"lengthSeconds": info["duration"],
				"allowRatings": None,
				"rating": info["average_rating"],
				"isListed": None,
				"liveNow": None,
				"isUpcoming": None,
				"dashUrl": "{}/api/manifest/dash/id/{}".format(configuration.website_origin, info["id"]),
				"second__providedDashUrl": None,
				"adaptiveFormats": [{
					"index": None,
					"bitrate": str(int(format["tbr"]*1000)),
					"init": None,
					"url": format["url"],
					"itag": format["format_id"],
					"type": format_type(format),
					"second__mime": format_mime(format),
					"second__codecs": format_codecs(format),
					"clen": str(format["filesize"]),
					"lmt": None,
					"projectionType": None,
					"fps": format["fps"],
					"container": format["ext"],
					"encoding": None,
					"resolution": format["format_note"],
					"qualityLabel": format["format_note"],
					"second__width": format["width"],
					"second__height": format["height"]
				} for format in info["formats"] if format_is_adaptive(format)],
				"formatStreams": [{
					"url": format["url"],
					"itag": format["format_id"],
					"type": format_type(format),
					"second__mime": format_mime(format),
					"quality": None,
					"fps": format["fps"],
					"container": format["ext"],
					"encoding": None,
					"resolution": format["format_note"],
					"qualityLabel": format["format_note"],
					"size": "{}x{}".format(format["width"], format["height"]),
					"second__width": format["width"],
					"second__height": format["height"]
				} for format in info["formats"] if not format_is_adaptive(format)],
				"captions": [],
				"recommendedVideos": []
			}

			# Now try to get more stuff by manually examining the saved file
			# Figure out what the name of the saved file was
			recommendations = []
			created_files = [f for f in os.listdir() if f.startswith("{}_".format(info["id"]))]
			possible_files = [f for f in created_files if f.startswith("{}_https_-_www.youtube.com".format(info["id"]))]
			try:
				if len(possible_files) == 1:
					filename = possible_files[0]
					with open(filename) as file:
						r_yt_player_config = re.compile(r"""^\s*[^"]+"cfg"[^"]+ytplayer\.config = (\{.*\});ytplayer\.web_player_context_config = {".""", re.M)
						content = file.read()

						yt_initial_data = extract_yt_initial_data(content)
						views = yt_initial_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]\
							["videoPrimaryInfoRenderer"]["viewCount"]["videoViewCountRenderer"]
						result["second__viewCountText"] = get_view_count_text_or_recommended(views)
						if "shortViewCount" in views:
							result["second__viewCountTextShort"] = views["shortViewCount"]["simpleText"]
						recommendations = yt_initial_data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]\
							["secondaryResults"]["results"]

						def get_useful_recommendation_data(r):
							if "compactVideoRenderer" in r:
								return r["compactVideoRenderer"]
							if "compactAutoplayRenderer" in r:
								return r["compactAutoplayRenderer"]["contents"][0]["compactVideoRenderer"]
							return None

						result["recommendedVideos"] = list({
							"videoId": r["videoId"],
							"title": r["title"]["simpleText"],
							"videoThumbnails": generate_video_thumbnails(r["videoId"]),
							"author": combine_runs(r["longBylineText"]),
							"authorUrl": r["longBylineText"]["runs"][0]["navigationEndpoint"]["commandMetadata"]["webCommandMetadata"]["url"],
							"authorId": r["longBylineText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"],
							"lengthSeconds": get_length_or_live_now(r),
							"second__lengthText": get_length_text_or_live_now(r),
							"viewCountText": get_view_count_text_or_recommended(r),
							"viewCount": get_view_count_or_recommended(r),
							"second__liveNow": is_live(r)
						} for r in [get_useful_recommendation_data(r) for r in recommendations if get_useful_recommendation_data(r)])

						m_yt_player_config = re.search(r_yt_player_config, content)
						if m_yt_player_config:
							yt_player_config = json.loads(m_yt_player_config.group(1))
							player_response = json.loads(yt_player_config["args"]["player_response"])
							if "dashManifestUrl" in player_response["streamingData"]:
								result["second__providedDashUrl"] = player_response["streamingData"]["dashManifestUrl"]
							result["liveNow"] = player_response["videoDetails"]["isLiveContent"]
							# result = player_response
							# return result
							itagDict = {}
							for f in player_response["streamingData"]["adaptiveFormats"]:
								if "indexRange" in f:
									itagDict[str(f["itag"])] = {
										"initRange": f["initRange"],
										"indexRange": f["indexRange"],
										"audioChannels": f["audioChannels"] if "audioChannels" in f else None
									}
							for f in result["adaptiveFormats"]:
								if f["itag"] in itagDict:
									i = itagDict[f["itag"]]
									f["init"] = "{}-{}".format(i["initRange"]["start"], i["initRange"]["end"])
									f["index"] = "{}-{}".format(i["indexRange"]["start"], i["indexRange"]["end"])
									f["second__audioChannels"] = i["audioChannels"]

			except Exception:
				print("messed up extracting recommendations.")
				traceback.print_exc()

			finally:
				for file in created_files:
					os.unlink(file)

				self.video_cache[id] = result
				return result

		except youtube_dl.DownloadError:
			return {
				"error": "Video unavailable",
				"identifier": "VIDEO_DOES_NOT_EXIST"
			}

	@cherrypy.expose
	@cherrypy.tools.encode()
	def manifest(self, id, **kwargs):
		id = id.split(".")[0] # remove extension if present
		video = self.videos(id)

		if "error" in video:
			return video

		if video["second__providedDashUrl"]:
			with requests.get(video["second__providedDashUrl"]) as r:
				r.raise_for_status()
				cherrypy.response.headers["content-type"] = r.headers["content-type"]
				return r

		adaptation_sets_dict = {}
		for f in video["adaptiveFormats"]:
			mime = f["second__mime"]
			if mime == "audio/m4a":
				mime = "audio/mp4"
			if not mime in adaptation_sets_dict:
				adaptation_sets_dict[mime] = []
			ads = adaptation_sets_dict[mime]

			representation_attributes = {"id": f["itag"], "codecs": ", ".join(f["second__codecs"]), "bandwidth": f["bitrate"]}
			if f["second__width"]:
				representation_attributes["width"] = str(f["second__width"])
				representation_attributes["height"] = str(f["second__height"])
				representation_attributes["startWithSAP"] = "1"
				representation_attributes["maxPlayoutRate"] = "1"
				representation_attributes["frameRate"] = str(f["fps"])
			representation = ET.Element("Representation", representation_attributes)
			if f.get("second__audioChannels"):
				ET.SubElement(representation, "AudioChannelConfiguration", {"schemeIdUri": "urn:mpeg:dash:23003:3:audio_channel_configuration:2011", "value": str(f["second__audioChannels"])})
			ET.SubElement(representation, "BaseURL").text = f["url"]
			et_segment_base = ET.SubElement(representation, "SegmentBase", {"indexRange": f["index"]})
			ET.SubElement(et_segment_base, "Initialization", {"range": f["init"]})
			ads.append(representation)

		s_meta = B'<?xml version="1.0" encoding="UTF-8"?>'
		et_mpd = ET.Element("MPD", {"xmlns": "urn:mpeg:dash:schema:mpd:2011", "profiles": "urn:mpeg:dash:profile:full:2011", "minBufferTime": "PT1.5S", "type": "static", "mediaPresentationDuration": "PT282S"})
		et_period = ET.SubElement(et_mpd, "Period")
		for (index, key) in list(enumerate(adaptation_sets_dict)):
			ads = adaptation_sets_dict[key]
			et_adaptation_set = ET.SubElement(et_period, "AdaptationSet", {"id": str(index), "mimeType": key, "startWithSAP": "1", "subsegmentAlignment": "true"})
			for representation in ads:
				et_adaptation_set.append(representation)
		manifest = s_meta + ET.tostring(et_mpd)

		cherrypy.response.headers["content-type"] = "application/dash+xml"
		return manifest

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def channels(self, *suffix, **kwargs):
		ucid = ""
		part = ""
		if len(suffix) == 1:
			ucid = suffix[0]
		else: # len(suffix) >= 2
			if suffix[0] == "videos" or suffix[0] == "latest" or suffix[0] == "playlists":
				[part, ucid] = suffix
			else:
				[ucid, part] = suffix

		if part == "playlists":
			return []

		if part == "latest":
			# use RSS
			with requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(ucid)) as r:
				r.raise_for_status()
				feed = ET.fromstring(r.content)
				author_container = feed.find("{http://www.w3.org/2005/Atom}author")
				author = author_container.find("{http://www.w3.org/2005/Atom}name").text
				author_url = author_container.find("{http://www.w3.org/2005/Atom}uri").text
				channel_id = feed.find("{http://www.youtube.com/xml/schemas/2015}channelId").text
				results = []
				for entry in feed.findall("{http://www.w3.org/2005/Atom}entry"):
					id = entry.find("{http://www.youtube.com/xml/schemas/2015}videoId").text
					media_group = entry.find("{http://search.yahoo.com/mrss/}group")
					description = media_group.find("{http://search.yahoo.com/mrss/}description").text
					media_community = media_group.find("{http://search.yahoo.com/mrss/}community")
					results.append({
						"type": "video",
						"title": entry.find("{http://www.w3.org/2005/Atom}title").text,
						"videoId": id,
						"author": author,
						"authorId": channel_id,
						"authorUrl": author_url,
						"videoThumbnails": generate_video_thumbnails(id),
						"description": description,
						"descriptionHtml": add_html_links(escape_html_textcontent(description)),
						"viewCount": int(media_community.find("{http://search.yahoo.com/mrss/}statistics").attrib["views"]),
						"published": int(dateutil.parser.isoparse(entry.find("{http://www.w3.org/2005/Atom}published").text).timestamp()),
						"lengthSeconds": None,
						"liveNow": None,
						"paid": None,
						"premium": None,
						"isUpcoming": None
					})
				return results

		else:
			if ucid in self.channel_cache:
				if part == "":
					return self.channel_cache[ucid]
				else: # part == "videos"
					return self.channel_cache[ucid]["latestVideos"]

			channel_type = "channel" if len(ucid) == 24 and ucid[:2] == "UC" else "user"
			with requests.get("https://www.youtube.com/{}/{}/videos".format(channel_type, ucid)) as r:
				r.raise_for_status()
				yt_initial_data = extract_yt_initial_data(r.content.decode("utf8"))
				header = yt_initial_data["header"]["c4TabbedHeaderRenderer"]
				author = header["title"]
				author_id = header["channelId"]
				author_url = header["navigationEndpoint"]["commandMetadata"]["webCommandMetadata"]["url"]
				author_banners = header["banner"]["thumbnails"]
				for t in author_banners:
					t["url"] = normalise_url_protocol(t["url"])
				author_thumbnails = generate_full_author_thumbnails(header["avatar"]["thumbnails"])
				subscriber_count = combine_runs(header["subscriberCountText"])
				description = yt_initial_data["metadata"]["channelMetadataRenderer"]["description"]
				allowed_regions = yt_initial_data["metadata"]["channelMetadataRenderer"]["availableCountryCodes"]
				tabs = yt_initial_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
				videos_tab = next(tab["tabRenderer"] for tab in tabs if tab["tabRenderer"]["title"] == "Videos")
				videos = (
					v["gridVideoRenderer"] for v in
					videos_tab["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"][0]["gridRenderer"]["items"]
				)
				latest_videos = []
				for v in videos:
					length_text = "LIVE"
					length_seconds = -1
					for o in v["thumbnailOverlays"]:
						if "thumbnailOverlayTimeStatusRenderer" in o:
							length_text = combine_runs(o["thumbnailOverlayTimeStatusRenderer"]["text"])
							if o["thumbnailOverlayTimeStatusRenderer"]["style"] != "LIVE":
								length_seconds = length_text_to_seconds(length_text)
					published = 0
					published_text = "Live now"
					if "publishedTimeText" in v:
						published_text = v["publishedTimeText"]["simpleText"]
						published = past_text_to_time(published_text)
					latest_videos.append({
						"type": "video",
						"title": combine_runs(v["title"]),
						"videoId": v["videoId"],
						"author": author,
						"authorId": author_id,
						"authorUrl": author_url,
						"videoThumbnails": generate_video_thumbnails(v["videoId"]),
						"description": "",
						"descriptionHtml": "",
						"viewCount": view_count_text_to_number(combine_runs(v["viewCountText"])),
						"second__viewCountText": combine_runs(v["viewCountText"]),
						"second__viewCountTextShort": combine_runs(v["shortViewCountText"]),
						"published": published,
						"publishedText": published_text,
						"lengthSeconds": length_seconds,
						"second__lengthText": length_text,
						"liveNow": None,
						"paid": None,
						"premium": None,
						"isUpcoming": None
					})

				channel = {
					"author": author,
					"authorId": author_id,
					"authorUrl": author_url,
					"authorBanners": author_banners,
					"authorThumbnails": author_thumbnails,
					"subCount": uncompress_counter(subscriber_count.split(" ")[0]),
					"second__subCountText": subscriber_count,
					"totalViews": None,
					"joined": None,
					"paid": None,
					"autoGenerated": None,
					"isFamilyFriendly": None,
					"description": description,
					"descriptionHtml": add_html_links(escape_html_textcontent(description)),
					"allowedRegions": allowed_regions,
					"latestVideos": latest_videos,
					"relatedChannels": []
				}

				self.channel_cache[ucid] = channel

				if part == "":
					return channel
				else:
					return latest_videos

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def search(self, *suffix, q, **kwargs):
		if suffix == ("suggestions",):
			return self.suggestions(q=q)

		if q in self.search_cache:
			return self.search_cache[q]

		try:
			with requests.get("https://www.youtube.com/results", params={"q": q}) as r:
				r.raise_for_status()
				content = r.content.decode("utf8")
				yt_initial_data = extract_yt_initial_data(content)
				items = yt_initial_data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
				results = []
				for item in items:
					if "videoRenderer" in item:
						video = item["videoRenderer"]
						published = 0
						published_text = "Live now"
						if "publishedTimeText" in video:
							published_text = video["publishedTimeText"]["simpleText"]
							published = past_text_to_time(published_text)
						results.append({
							"type": "video",
							"title": combine_runs(video["title"]),
							"videoId": video["videoId"],
							"author": combine_runs(video["longBylineText"]),
							"authorId": video["longBylineText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"],
							"authorUrl": video["longBylineText"]["runs"][0]["navigationEndpoint"]["commandMetadata"]["webCommandMetadata"]["url"],
							"videoThumbnails": generate_video_thumbnails(video["videoId"]),
							"description": combine_runs(video["descriptionSnippet"]) if "descriptionSnippet" in video else "",
							"descriptionHtml": combine_runs_html(video["descriptionSnippet"]) if "descriptionSnippet" in video else "",
							"viewCount": get_view_count_or_recommended(video),
							"second__viewCountText": get_view_count_text_or_recommended(video),
							"published": published,
							"publishedText": published_text,
							"lengthSeconds": get_length_or_live_now(video),
							"second__lengthText": get_length_text_or_live_now(video),
							"liveNow": is_live(video),
							"paid": None,
							"premium": None,
							"isUpcoming": None
						})
				self.search_cache[q] = results # only cache full extraction
				return results

		except Exception:
			print("messed up extracting search, using youtube-dl instead")
			traceback.print_exc()

			info = ytdl.extract_info("ytsearchall:{}".format(q), download=False)
			return [{
				"type": "video",
				"title": video["title"],
				"videoId": video["id"],
				"author": None,
				"authorId": None,
				"authorUrl": None,
				"videoThumbnails": generate_video_thumbnails(video["id"]),
				"description": None,
				"descriptionHtml": None,
				"viewCount": None,
				"published": None,
				"publishedText": None,
				"lengthSeconds": None,
				"liveNow": None,
				"paid": None,
				"premium": None,
				"isUpcoming": None
			} for video in info["entries"] if "title" in video]

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def suggestions(self, *, q, **kwargs):
		if q in self.search_suggestions_cache:
			return self.search_suggestions_cache[q]

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
			self.search_suggestions_cache[q] = result
			return result

	@cherrypy.expose
	def vi(self, id, file):
		with requests.get("https://i.ytimg.com/vi/{}/{}".format(id, file)) as r:
			r.raise_for_status()
			cherrypy.response.headers["content-type"] = r.headers["content-type"]
			return r # no idea if this is a good way to do it, but it definitely works! :D

cherrypy.config.update({"server.socket_port": 3000, "server.socket_host": "0.0.0.0"})
cherrypy.quickstart(Second())
