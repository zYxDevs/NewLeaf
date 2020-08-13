import requests
import traceback
import youtube_dl
from tools.converters import *
from tools.extractors import extract_yt_initial_data
from cachetools import TTLCache

search_cache = TTLCache(maxsize=50, ttl=300)

ytdl_opts = {
	"quiet": True,
	"dump_single_json": True,
	"playlist_items": "1-100",
	"extract_flat": "in_playlist"
}
ytdl = youtube_dl.YoutubeDL(ytdl_opts)

def extract_search(q):
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
			search_cache[q] = results # only cache full extraction
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
