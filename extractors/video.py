import configuration
import datetime
import json
import os
import re
import traceback
import youtube_dl
import urllib.error
from tools.converters import *
from tools.extractors import extract_yt_initial_data
from math import floor
from cachetools import TTLCache

video_cache = TTLCache(maxsize=50, ttl=300)

ytdl_opts = {
	"quiet": True,
	"dump_single_json": True,
	"playlist_items": "1-100",
	"extract_flat": "in_playlist",
	"write_pages": True,
        "source_address": "0.0.0.0"
}
ytdl = youtube_dl.YoutubeDL(ytdl_opts)

def get_created_files(id):
	if id[0] == "-":
		id = "_" + id[1:] # youtube-dl changes - to _ at the start, presumably to not accidentally trigger switches with * in shell
	return (f for f in os.listdir() if f.startswith("{}_".format(id)))

def format_order(format):
	# most significant to least significant
	# key, max, order, transform
	# asc: lower number comes first, desc: higher number comes first
	spec = [
		["second__height", 8000, "desc", lambda x: floor(x/96) if x else 0],
		["fps", 100, "desc", lambda x: floor(x/10) if x else 0],
		["type", " "*60, "asc", lambda x: len(x)],
	]
	total = 0
	for i in range(len(spec)):
		s = spec[i]
		diff = s[3](format[s[0]])
		if s[2] == "asc":
			diff = s[3](s[1]) - diff
		total += diff
		if i+1 < len(spec):
			s2 = spec[i+1]
			total *= s2[3](s2[1])
	return -total

def extract_video(id):
	if id in video_cache:
		return video_cache[id]

	result = None

	try:
		info = ytdl.extract_info(id, download=False)

		year = int(info["upload_date"][:4])
		month = int(info["upload_date"][4:6])
		day = int(info["upload_date"][6:8])
		published = int(datetime.datetime(year, month, day).timestamp())

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
			"likeCount": 0,
			"dislikeCount": 0,
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
			"adaptiveFormats": [],
			"formatStreams": [],
			"captions": [],
			"recommendedVideos": []
		}

		for format in info["formats"]:
			# Adaptive formats have either audio or video, format streams have both
			is_adaptive = format["acodec"] == "none" or format["vcodec"] == "none"
			sense = "video" if format["vcodec"] != "none" else "audio"
			mime = sense + "/" + format["ext"]
			codecs = []
			if format["vcodec"] != "none":
				codecs.append(format["vcodec"])
			if format["acodec"] != "none":
				codecs.append(format["acodec"])
			result_type = '{}; codecs="{}"'.format(mime, ", ".join(codecs))

			if is_adaptive:
				url = ""
				if format["protocol"] == "http_dash_segments":
					# this is http dash, which is annoying and doesn't work in <video>.
					# we have a fragment_base_url, which seems to be playable for all audio, but only with certain video itags??? very confused
					if format["acodec"] == "none" and format["format_id"] not in ["134", "136"]:
						continue
					url = format["fragment_base_url"]
				else: # just a normal media file
					url = format["url"]
				result["adaptiveFormats"].append({
					"index": None,
					"bitrate": str(int(format["tbr"]*1000)),
					"init": None,
					"url": url,
					"itag": format["format_id"],
					"type": result_type,
					"second__mime": mime,
					"second__codecs": codecs,
					"clen": str(format["filesize"]) if format["filesize"] else None,
					"lmt": None,
					"projectionType": None,
					"fps": format["fps"],
					"container": format["ext"],
					"encoding": None,
					"resolution": format["format_note"],
					"qualityLabel": format["format_note"],
					"second__width": format["width"],
					"second__height": format["height"],
					"second__audioChannels": None,
					"second__order": 0
				})
			else: # format is not adaptive
				result["formatStreams"].append({
					"url": format["url"],
					"itag": format["format_id"],
					"type": result_type,
					"second__mime": mime,
					"quality": None,
					"fps": format["fps"],
					"container": format["ext"],
					"encoding": None,
					"resolution": format["format_note"],
					"qualityLabel": format["format_note"],
					"size": str(format["width"]) + "x" + str(format["height"]),
					"second__width": format["width"],
					"second__height": format["height"]
				})

		result = get_more_stuff_from_file(info["id"], result)

		return result

	except youtube_dl.DownloadError as e:
		if isinstance(e.exc_info[1], urllib.error.HTTPError):
			if e.exc_info[1].code == 429:
				result = {
					"error": "Could not extract video info. Instance is likely blocked.",
					"identifier": "RATE_LIMITED_BY_YOUTUBE"
				}
			else:
				result = {
					"error": "Received unexpected status code {}.".format(e.exc_info[1].code)
				}
		else:
			result = {
				"error": "Unknown download error."
			}

	except Exception:
		traceback.print_exc()
		print("messed up in original transform.")

	finally:
		created_files = get_created_files(id)
		for file in created_files:
			os.unlink(file)
		return result

def get_more_stuff_from_file(id, result):
	# Figure out what the name of the saved file was
	recommendations = []
	created_files = get_created_files(id)
	possible_files = [f for f in created_files if f[11:].startswith("_https_-_www.youtube.com")]
	try:
		if len(possible_files) == 1:
			filename = possible_files[0]
			with open(filename) as file:
				r_yt_player_config = re.compile(r"""^\s*[^"]+"cfg"[^"]+ytplayer\.config = (\{.*\});ytplayer\.web_player_context_config = {".""", re.M)
				content = file.read()

				yt_initial_data = extract_yt_initial_data(content)

				main_video = yt_initial_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]["videoPrimaryInfoRenderer"]
				views = main_video["viewCount"]["videoViewCountRenderer"]
				result["second__viewCountText"] = get_view_count_text_or_recommended(views)
				if "shortViewCount" in views:
					result["second__viewCountTextShort"] = views["shortViewCount"]["simpleText"]
				if "sentimentBar" in main_video:
					sentiment = main_video["sentimentBar"]["sentimentBarRenderer"]["tooltip"]
					result["likeCount"] = view_count_text_to_number(sentiment.split(" / ")[0])
					result["dislikeCount"] = view_count_text_to_number(sentiment.split(" / ")[1])
					result["allowRatings"] = True
				else:
					result["allowRatings"] = False
				recommendations = yt_initial_data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]\
					["secondaryResults"]["results"]

				# result = yt_initial_data
				# return result

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
							if f["second__height"]:
								resolution = str(f["second__height"]) + "p"
								f["resolution"] = resolution
								label = resolution
								if f["fps"] > 30:
									label += str(f["fps"])
								f["qualityLabel"] = label
							f["second__order"] = format_order(f)

	except Exception:
		print("messed up extracting recommendations.")
		traceback.print_exc()

	finally:
		video_cache[id] = result
		return result
