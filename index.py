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
from extractors.video import extract_video
from extractors.channel import extract_channel, extract_channel_videos, extract_channel_latest
from extractors.manifest import extract_manifest
from extractors.search import extract_search
from extractors.suggestions import extract_search_suggestions

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
		return extract_video(id)

	@cherrypy.expose
	@cherrypy.tools.encode()
	def manifest(self, id, **kwargs):
		result = extract_manifest(id)
		if type(result) is dict:
			cherrypy.response.headers["content-type"] = "application/json"
			return bytes(json.dumps(result), "utf8")
		elif type(result) is requests.models.Response:
			cherrypy.response.headers["content-type"] = result.headers["content-type"]
			return result
		else:
			cherrypy.response.headers["content-type"] = "application/dash+xml"
			return result

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def channels(self, *suffix, **kwargs):
		ucid = ""
		part = ""
		possible_parts = ("videos", "latest", "playlists")
		if len(suffix) == 1:
			ucid = suffix[0]
		else: # len(suffix) >= 2
			if suffix[0] in possible_parts:
				[part, ucid] = suffix
			elif suffix[1] in possible_parts:
				[ucid, part] = suffix
			else:
				return {
					error: "Two components specified in URL, but neither component was recognised as a part keyword.",
					identifier: "PART_KEYWORD_NOT_RECOGNISED"
				}

		if part == "playlists":
			return []
		elif part == "latest":
			return extract_channel_latest(ucid)
		elif part == "videos":
			return extract_channel_videos(ucid)
		else: # part == "", so extract whole channel
			return extract_channel(ucid)

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def search(self, *suffix, q, **kwargs):
		if suffix == ("suggestions",):
			return self.suggestions(q=q)

		return extract_search(q)

	@cherrypy.expose
	@cherrypy.tools.json_out()
	def suggestions(self, *, q, **kwargs):
		return extract_search_suggestions(q)

	@cherrypy.expose
	def vi(self, id, file):
		with requests.get("https://i.ytimg.com/vi/{}/{}".format(id, file)) as r:
			r.raise_for_status()
			cherrypy.response.headers["content-type"] = r.headers["content-type"]
			return r # no idea if this is a good way to do it, but it definitely works! :D

cherrypy.config.update({"server.socket_port": 3000, "server.socket_host": "0.0.0.0"})
cherrypy.quickstart(Second())
