import requests
import xml.etree.ElementTree as ET
from extractors.video import extract_video

def extract_manifest(id):
	id = id.split(".")[0] # remove extension if present

	video = extract_video(id)

	if "error" in video:
		return video

	if video["second__providedDashUrl"]:
		with requests.get(video["second__providedDashUrl"]) as r:
			r.raise_for_status()
			return r

	adaptation_sets_dict = {}
	for f in video["adaptiveFormats"]:
		if not f["index"] or not f["init"]: # video extraction was not complete
			return {
				"error": "Video extraction was not complete, not enough fields are available to generate manifest",
				"identifier": "VIDEO_EXTRACTION_NOT_COMPLETE_FOR_MANIFEST"
			}

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

	return manifest
