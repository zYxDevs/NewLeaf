import cherrypy
import json
import pathlib
import requests
import yt_dlp
from extractors.video import extract_video
from extractors.channel import extract_channel, extract_channel_videos, extract_channel_latest
from extractors.manifest import extract_manifest
from extractors.search import extract_search
from extractors.suggestions import extract_search_suggestions
from extractors.captions import extract_captions
import configuration

@cherrypy.tools.register("before_finalize", priority=60)
def custom_headers():
	cherrypy.response.headers["access-control-allow-origin"] = "*"

class NewLeaf(object):
	def _cp_dispatch(self, vpath):
		if vpath[:4] == ["api", "manifest", "dash", "id"]:
			vpath[:4] = ["manifest"]
			return self

		if vpath[:2] == ["api", "v1"]:
			endpoints = [
				["channels", 1, 2],
				["videos", 1, 1],
				["search", 0, 1],
				["captions", 1, 1]
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
					"error": "Two components specified in URL, but neither component was recognised as a part keyword.",
					"identifier": "PART_KEYWORD_NOT_RECOGNISED"
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
	def captions(self, id, **kwargs):
		try:
			result = extract_captions(id, **kwargs)
			if type(result) is dict:
				cherrypy.response.headers["content-type"] = "application/json"
				return bytes(json.dumps(result), "utf8")
			else:
				cherrypy.response.headers["content-type"] = "text/vtt; charset=UTF-8"
				return result

		except StopIteration:
			cherrypy.response.status = "400"
			cherrypy.response.headers["content-type"] = "application/json"
			return bytes(json.dumps({
				"error": "No captions matching that language or label",
				"identifier": "NO_MATCHING_CAPTIONS"
			}), "utf8")

	@cherrypy.expose
	def vi(self, id, file):
		with requests.get("https://i.ytimg.com/vi/{}/{}".format(id, file)) as r:
			r.raise_for_status()
			cherrypy.response.headers["content-type"] = r.headers["content-type"]
			return r # no idea if this is a good way to do it, but it definitely works! :D

	@cherrypy.expose
	def ggpht(self, *path):
		with requests.get("https://yt3.ggpht.com/{}".format("/".join(path))) as r:
			r.raise_for_status()
			cherrypy.response.headers["content-type"] = r.headers["content-type"]
			return r

bind_port = getattr(configuration, "bind_port", 3000)
bind_host = getattr(configuration, "bind_host", "0.0.0.0")
server_root = pathlib.Path(__file__).parent.joinpath("root")

cherrypy.config.update({"server.socket_port": bind_port, "server.socket_host": bind_host})
cherrypy.quickstart(NewLeaf(), "/", {
	"/": {
		"tools.custom_headers.on": True,
		"tools.staticdir.on": True,
		"tools.staticdir.dir": str(server_root.absolute()),
		"tools.staticdir.index": "index.html"
	}
})
