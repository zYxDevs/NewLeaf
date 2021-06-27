import json
import requests
import urllib.parse
from tools.converters import *
from tools.extractors import extract_yt_initial_data, extract_yt_cfg, eu_consent_cookie

def extract_comments(id, **kwargs):
	s = requests.session()
	s.headers.update({"accept-language": "en-US,en;q=0.9"})
	s.cookies.set("CONSENT", eu_consent_cookie().get("CONSENT"))
	with s.get("https://www.youtube.com/watch?v={}".format(id)) as r:
		r.raise_for_status()
		yt_initial_data = extract_yt_initial_data(r.content.decode("utf8"))
		item = yt_initial_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][2]["itemSectionRenderer"]
		continuation = item["continuations"][0]["nextContinuationData"]["continuation"]
		itct = item["continuations"][0]["nextContinuationData"]["clickTrackingParams"]
		xsrf_token = extract_yt_cfg(r.content.decode("utf8")).get("XSRF_TOKEN", None)
		if not xsrf_token:
			cherrypy.response.status = 500
			return {
				"error": "NewLeaf was unable to obtain XSRF_TOKEN from ytcfg.",
				"identifier": "XSRF_TOKEN_NOT_FOUND"
			}
		url = "https://www.youtube.com/comment_service_ajax?action_get_comments=1&pbj=1&ctoken={}&continuation={}&type=next&itct={}".format(continuation, continuation, urllib.parse.quote_plus(itct))
		with s.post(url, headers={"x-youtube-client-name": "1", "x-youtube-client-version": "2.20210422.04.00"}, data={"session_token": xsrf_token}) as rr:
			data = json.loads(rr.content.decode("utf8"))
			return {
				"videoId": id,
				"comments": [
					{
						"author": c["commentThreadRenderer"]["comment"]["commentRenderer"]["authorText"]["simpleText"],
						"authorThumbnails": [x for x in c["commentThreadRenderer"]["comment"]["commentRenderer"]["authorThumbnail"]["thumbnails"]],
						"authorId": c["commentThreadRenderer"]["comment"]["commentRenderer"]["authorEndpoint"]["browseEndpoint"]["browseId"],
						"authorUrl": c["commentThreadRenderer"]["comment"]["commentRenderer"]["authorEndpoint"]["browseEndpoint"]["canonicalBaseUrl"],
						"isEdited": " (edited)" in "".join([x["text"] for x in c["commentThreadRenderer"]["comment"]["commentRenderer"]["publishedTimeText"]["runs"]]),
						"content": "".join([x["text"] for x in c["commentThreadRenderer"]["comment"]["commentRenderer"]["contentText"]["runs"]]),
						"contentHtml": escape_html_textcontent("".join([x["text"] for x in c["commentThreadRenderer"]["comment"]["commentRenderer"]["contentText"]["runs"]])),
						"publishedText": "".join([x["text"] for x in c["commentThreadRenderer"]["comment"]["commentRenderer"]["publishedTimeText"]["runs"]]),
						# "likeCount": int(c["commentThreadRenderer"]["comment"]["commentRenderer"]["voteCount"]["simpleText"].replace(",", ""))
						"commentId": c["commentThreadRenderer"]["comment"]["commentRenderer"]["commentId"],
						"authorIsChannelOwner": c["commentThreadRenderer"]["comment"]["commentRenderer"]["authorIsChannelOwner"],
						# "replies": {
						# 	"replyCount": c["commentThreadRenderer"]["comment"]["commentRenderer"]["replyCount"]
						# }
					} for c in data["response"]["continuationContents"]["itemSectionContinuation"]["contents"]
				]
			}
