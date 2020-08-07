import cherrypy
import json
import youtube_dl
import datetime
import os
import re
import json
import traceback

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

class Second(object):
	def _cp_dispatch(self, vpath):
		if vpath[:2] == ["api", "v1"]:
			endpoints = [
				["channels", 1, 2],
				["videos", 1, 1],
				["search", 0, 0]
			]
			for e in endpoints:
				if vpath[2] == e[0] and len(vpath) >= e[1]+3 and len(vpath) <= e[2]+3:
					vpath[:3] = [e[0]]
					return self

		return vpath

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def videos(self, id):
		try:
			info = ytdl_save.extract_info(id, download=False)

			year = int(info["upload_date"][:4])
			month = int(info["upload_date"][4:6])
			day = int(info["upload_date"][6:8])

			# Adaptive formats have either audio or video, format streams have both
			def format_is_adaptive(format):
				return format["acodec"] == "none" or format["vcodec"] == "none"

			# just the "type" field
			def format_type(format):
				sense = "audio"
				codecs = []
				if format["vcodec"] != "none":
					sense = "video"
					codecs.append(format["vcodec"])
				if format["acodec"] != "none":
					codecs.append(format["acodec"])
				return '{}/{}; codecs="{}"'.format(sense, format["ext"], ", ".join(codecs))

			result = {
				"type": "video",
				"title": info["title"],
				"videoId": info["id"],
				"videoThumbnails": None,
				"storyboards": None,
				"description": info["description"],
				"descriptionHtml": None,
				"published": int(datetime.datetime(year, month, day).timestamp()),
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
				"dashUrl": None,
				"adaptiveFormats": list({
					"index": None,
					"bitrate": str(int(format["tbr"]*1000)),
					"init": None,
					"url": format["url"],
					"itag": format["format_id"],
					"type": format_type(format),
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
				} for format in info["formats"] if format_is_adaptive(format)),
				"formatStreams": list({
					"url": format["url"],
					"itag": format["format_id"],
					"type": format_type(format),
					"quality": None,
					"fps": format["fps"],
					"container": format["ext"],
					"encoding": None,
					"resolution": format["format_note"],
					"qualityLabel": format["format_note"],
					"size": "{}x{}".format(format["width"], format["height"]),
					"second__width": format["width"],
					"second__height": format["height"]
				} for format in info["formats"] if not format_is_adaptive(format)),
				"captions": [],
				"recommendedVideos": []
			}

			# Now try to get more stuff by manually examining the saved file
			# Figure out what the name of the saved file was
			possible_files = [f for f in os.listdir() if f.startswith("{}_".format(info["id"]))]
			try:
				if len(possible_files) == 1:
					filename = possible_files[0]
					with open(filename) as file:
						r = re.compile(r"""^\s*window\["ytInitialData"\] = (\{.*\});\n?$""")
						for line in file:
							match_result = re.search(r, line)
							if match_result:
								yt_initial_data = json.loads(match_result.group(1))
								views = yt_initial_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]\
									["videoPrimaryInfoRenderer"]["viewCount"]["videoViewCountRenderer"]
								result["second__viewCountText"] = views["viewCount"]["simpleText"]
								result["second__viewCountTextShort"] = views["shortViewCount"]["simpleText"]
								recommendations = yt_initial_data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]\
									["secondaryResults"]["results"]

								def get_useful_recommendation_data(r):
									if "compactVideoRenderer" in r:
										return r["compactVideoRenderer"]
									if "compactAutoplayRenderer" in r:
										return r["compactAutoplayRenderer"]["contents"][0]["compactVideoRenderer"]
									return None

								def get_view_count(r):
									text = r["viewCountText"]["simpleText"]
									if text == "Recommended for you":
										return 0 # subject to change?
									else:
										return int(text.replace(",", "").split(" ")[0])

								def get_view_count_text(r):
									text = r["viewCountText"]["simpleText"]
									if text == "Recommended for you":
										return "Recommended for you" # subject to change?
									else:
										return text

								# result["recommendedVideos"] = recommendations
								# return result

								result["recommendedVideos"] = list({
									"videoId": r["videoId"],
									"title": r["title"]["simpleText"],
									"videoThumbnails": [],
									"author": r["longBylineText"]["runs"][0]["text"],
									"authorUrl": r["longBylineText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["canonicalBaseUrl"],
									"authorId": r["longBylineText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"],
									"lengthSeconds": length_text_to_seconds(r["lengthText"]["simpleText"]),
									"second__lengthText": r["lengthText"]["simpleText"],
									"viewCountText": get_view_count_text(r),
									"viewCount": get_view_count(r)
								} for r in [get_useful_recommendation_data(r) for r in recommendations if get_useful_recommendation_data(r)])

			except Exception:
				traceback.print_exc()

			finally:
				for file in possible_files:
					os.unlink(file)

				return result

		except youtube_dl.DownloadError:
			return {
				"error": "Video unavailable",
				"identifier": "VIDEO_DOES_NOT_EXIST"
			}

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def channels(self, *suffix):
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
					"videoThumbnails": [],
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
	def search(self, *, q, sort_by):
		info = ytdl.extract_info("ytsearchall:{}".format(q), download=False)
		return list({
			"type": "video",
			"title": video["title"],
			"videoId": video["id"],
			"author": None,
			"authorId": None,
			"authorUrl": None,
			"videoThumbnails": [],
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
		} for video in info["entries"] if "title" in video)

cherrypy.config.update({"server.socket_port": 3000})
cherrypy.quickstart(Second())
