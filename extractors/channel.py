import cherrypy
import dateutil.parser
import requests
import xml.etree.ElementTree as ET
from tools.converters import *
from tools.extractors import extract_yt_initial_data, eu_consent_cookie
from threading import Lock
from cachetools import TTLCache

channel_cache = TTLCache(maxsize=50, ttl=300)
channel_cache_lock = Lock()
channel_latest_cache = TTLCache(maxsize=500, ttl=300)
channel_latest_cache_lock = Lock()

def extract_channel(ucid):
	with channel_cache_lock:
		if ucid in channel_cache:
			return channel_cache[ucid]

	channel_type = "channel" if len(ucid) == 24 and ucid[:2] == "UC" else "user"
	with requests.get("https://www.youtube.com/{}/{}/videos?hl=en".format(channel_type, ucid), cookies=eu_consent_cookie()) as r:
		r.raise_for_status()
		yt_initial_data = extract_yt_initial_data(r.content.decode("utf8"))

		for alert in yt_initial_data.get("alerts", []):
			alert_text = combine_runs(alert["alertRenderer"]["text"])
			if alert_text == "This channel does not exist.":
				return {
					"error": alert_text,
					"identifier": "NOT_FOUND"
				}
			elif alert_text.startswith("This account has been terminated"):
				return {
					"error": alert_text,
					"identifier": "ACCOUNT_TERMINATED"
				}
			else:
				print("Seen alert text '{}'".format(alert_text))

		header = yt_initial_data["header"]["c4TabbedHeaderRenderer"] if "c4TabbedHeaderRenderer" in yt_initial_data["header"] else {}
		channel_metadata = yt_initial_data["metadata"]["channelMetadataRenderer"]

		if header:
			author = header["title"]
			author_id = header["channelId"]
			author_url = header["navigationEndpoint"]["commandMetadata"]["webCommandMetadata"]["url"]
		else:
			author = channel_metadata["title"]
			author_id = channel_metadata["externalId"]
			author_url = channel_metadata["channelUrl"]

		subscriber_count = combine_runs(header["subscriberCountText"]) if "subscriberCountText" in header else "Unknown subscribers"
		description = channel_metadata["description"]
		allowed_regions = channel_metadata["availableCountryCodes"]

		author_banners = []
		if "banner" in header:
			author_banners = header["banner"]["thumbnails"]
			for t in author_banners:
				t["url"] = normalise_url_protocol(t["url"])

		author_thumbnails = []
		avatar = header.get("avatar") or channel_metadata.get("avatar")
		if avatar:
			author_thumbnails = generate_full_author_thumbnails(avatar["thumbnails"])

		latest_videos = []
		tabs = yt_initial_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
		try:
			videos_tab = next(tab["tabRenderer"] for tab in tabs if tab["tabRenderer"]["title"] == "Videos")
			tab_parts = videos_tab["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"][0]
		except StopIteration:
			tab_parts = {}

		# check that the channel actually has videos - this may be replaced
		# with messageRenderer.text.simpleText == "This channel has no videos."
		if "gridRenderer" in tab_parts:
			videos = (
				v["gridVideoRenderer"] for v in tab_parts["gridRenderer"]["items"] if "gridVideoRenderer" in v
			)
			for v in videos:
				live = False
				is_upcoming = False
				length_text = "UNKNOWN"
				length_seconds = -1
				for o in v["thumbnailOverlays"]:
					if "thumbnailOverlayTimeStatusRenderer" in o:
						length_text = combine_runs(o["thumbnailOverlayTimeStatusRenderer"]["text"])
						length_text_style = o["thumbnailOverlayTimeStatusRenderer"]["style"]
						if length_text_style == "DEFAULT":
							length_seconds = length_text_to_seconds(length_text)
						elif length_text_style == "LIVE":
							live = True
						elif length_text_style == "UPCOMING":
							is_upcoming = True
				published = 0
				published_text = "Live now"
				premiere_timestamp = None
				if "publishedTimeText" in v:
					published_text = v["publishedTimeText"]["simpleText"]
					published = past_text_to_time(published_text)
				if "upcomingEventData" in v:
					premiere_timestamp = v["upcomingEventData"]["startTime"]
					published_text = time_to_past_text(int(premiere_timestamp))

				view_count_text = combine_runs(v["viewCountText"]) if "viewCountText" in v else None
				view_count_text_short = combine_runs(v["shortViewCountText"]) if "shortViewCountText" in v else None

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
					"viewCount": view_count_text_to_number(view_count_text),
					"second__viewCountText": view_count_text,
					"second__viewCountTextShort": view_count_text_short,
					"published": published,
					"publishedText": published_text,
					"lengthSeconds": length_seconds,
					"second__lengthText": length_text,
					"liveNow": live,
					"paid": None,
					"premium": None,
					"isUpcoming": is_upcoming,
					"premiereTimestamp": premiere_timestamp
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

		with channel_cache_lock:
			channel_cache[ucid] = channel

		return channel

def extract_channel_videos(ucid):
	channel = extract_channel(ucid)
	if "error" in channel:
		return channel
	else:
		return channel["latestVideos"]

def extract_channel_latest(ucid):
	with channel_latest_cache_lock:
		if ucid in channel_latest_cache:
			return channel_latest_cache[ucid]

	with requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(ucid)) as r:
		if r.status_code == 404:
			cherrypy.response.status = 404
			return {
				"error": "This channel does not exist.",
				"identifier": "NOT_FOUND"
			}

		feed = ET.fromstring(r.content)
		author_container = feed.find("{http://www.w3.org/2005/Atom}author")
		author = author_container.find("{http://www.w3.org/2005/Atom}name").text
		author_url = author_container.find("{http://www.w3.org/2005/Atom}uri").text
		channel_id = feed.find("{http://www.youtube.com/xml/schemas/2015}channelId").text
		results = []
		missing_published = False
		for entry in feed.findall("{http://www.w3.org/2005/Atom}entry"):
			id = entry.find("{http://www.youtube.com/xml/schemas/2015}videoId").text
			media_group = entry.find("{http://search.yahoo.com/mrss/}group")
			description = media_group.find("{http://search.yahoo.com/mrss/}description").text or ""
			media_community = media_group.find("{http://search.yahoo.com/mrss/}community")
			published_entry = entry.find("{http://www.w3.org/2005/Atom}published")
			if published_entry is not None: # sometimes youtube does not provide published dates, no idea why.
				published = int(dateutil.parser.isoparse(published_entry.text).timestamp())
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
					"published": published,
					"publishedText": time_to_past_text(published),
					"lengthSeconds": None,
					"liveNow": None,
					"paid": None,
					"premium": None,
					"isUpcoming": None
				})
			else:
				missing_published = True

		if len(results) == 0 and missing_published: # no results due to all missing published
			cherrypy.response.status = 503
			return {
				"error": "YouTube did not provide published dates for any feed items. This is usually temporary - refresh in a few minutes.",
				"identifier": "PUBLISHED_DATES_NOT_PROVIDED"
			}

		with channel_latest_cache_lock:
			channel_latest_cache[ucid] = results

		return results
