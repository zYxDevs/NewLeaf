import cherrypy
import json
import youtube_dl
import datetime

ytdl_opts = {
	"quiet": True,
	"dump_single_json": True,
	"playlist_items": "1-100",
	"extract_flat": "in_playlist"
}
ytdl = youtube_dl.YoutubeDL(ytdl_opts)

class HelloWorld(object):
	def _cp_dispatch(self, vpath):
		if vpath[:2] == ["api", "v1"] and len(vpath) >= 4:
			endpoints = ["channels", "videos"]
			for e in endpoints:
				if vpath[2] == e:
					vpath[:3] = [e]
					return self

		return vpath

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def videos(self, id):
		try:
			info = ytdl.extract_info(id, download=False)

			year = int(info["upload_date"][:4])
			month = int(info["upload_date"][4:6])
			day = int(info["upload_date"][6:8])

			def format_is_adaptive(format):
				return format["acodec"] == "none" or format["vcodec"] == "none"

			def format_type(format):
				sense = "audio"
				codecs = []
				if format["vcodec"] != "none":
					sense = "video"
					codecs.append(format["vcodec"])
				if format["acodec"] != "none":
					codecs.append(format["acodec"])
				return '{}/{}; codecs="{}"'.format(sense, format["ext"], ", ".join(codecs))

			return {
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

cherrypy.quickstart(HelloWorld())
