import configuration
import cherrypy
import json
import youtube_dl
import datetime
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

def view_count_text_to_number(text):
	return int(text.split(" ")[0].replace(",", ""))

def get_view_count_or_recommended(view_count_container):
	if "runs" in view_count_container["viewCountText"]: # has live viewers
		return int(combine_runs(view_count_container["viewCountText"]))
	else:
		text = view_count_container["viewCountText"]["simpleText"]
		if text == "Recommended for you":
			return 0 # subject to change?
		else:
			return view_count_text_to_number(text)

def get_view_count_text_or_recommended(view_count_container):
	if "runs" in view_count_container["viewCountText"]: # has live viewers
		text = combine_runs(view_count_container["viewCountText"])
	else: # has past views
		text = view_count_container["viewCountText"]["simpleText"]
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

class Second(object):
	def __init__(self):
		self.video_cache = TTLCache(maxsize=50, ttl=300)
		self.search_cache = TTLCache(maxsize=50, ttl=300)
		self.search_suggestions_cache = TTLCache(maxsize=200, ttl=60)

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
				"descriptionHtml": info["description"],
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
						r_yt_player_config = re.compile(r"""^\s*[^"]+"cfg"[^"]+ytplayer\.config = (\{.*\});ytplayer\.web_player_context_config = {".""")
						content = file.read()

						yt_initial_data = extract_yt_initial_data(content)
						views = yt_initial_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]\
							["videoPrimaryInfoRenderer"]["viewCount"]["videoViewCountRenderer"]
						result["second__viewCountText"] = get_view_count_text_or_recommended(views)
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
							"viewCount": get_view_count_or_recommended(r)
						} for r in [get_useful_recommendation_data(r) for r in recommendations if get_useful_recommendation_data(r)])

						m_yt_player_config = re.search(r_yt_player_config, line)
						if m_yt_player_config:
							yt_player_config = json.loads(m_yt_player_config.group(1))
							player_response = json.loads(yt_player_config["args"]["player_response"])
							if "dashManifestUrl" in player_response["streamingData"]:
								result["second__providedDashUrl"] = player_response["streamingData"]["dashManifestUrl"]
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
			if f["second__audioChannels"]:
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
			if suffix[0] == "videos" or suffix[0] == "latest":
				[part, ucid] = suffix
			else:
				[ucid, part] = suffix

		try:
			info = ytdl.extract_info("https://www.youtube.com/channel/{}".format(ucid), download=False)

			response = {
				"author": info["uploader"],
				"authorId": info["uploader_id"],
				"authorUrl": info["uploader_url"],
				"authorBanners": [],
				"authorThumbnails": [],
				"subCount": None,
				"totalViews": None,
				"joined": None,
				"paid": None,
				"autoGenerated": None,
				"isFamilyFriendly": None,
				"description": None,
				"descriptionHtml": None,
				"allowedRegions": [],
				"latestVideos": list({
					"type": "video",
					"title": video["title"],
					"videoId": video["id"],
					"author": info["uploader"],
					"authorId": info["uploader_id"],
					"authorUrl": info["uploader_url"],
					"videoThumbnails": generate_video_thumbnails(info["id"]),
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
				} for video in info["entries"]),
				"relatedChannels": []
			}

			if part == "videos" or part == "latest":
				return response["latestVideos"]
			else:
				return response

		except youtube_dl.DownloadError:
			return {
				"error": "This channel does not exist.",
				"identifier": "CHANNEL_DOES_NOT_EXIST"
			}

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
							"published": None,
							"publishedText": video["publishedTimeText"]["simpleText"],
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
