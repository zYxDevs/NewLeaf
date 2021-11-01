import os
import yt_dlp.utils

def get_created_files(id):
	# youtube-dl transforms filenames when saving, for example changing - to _ at the start to presumbly not trigger switches in shell, but also in other strange ways too
	sanitized_id = yt_dlp.utils.sanitize_filename(id)
	# all file names then have an underscore before the converted URL
	id += "_"
	sanitized_id += "_"

	return (f for f in os.listdir() if f.startswith(id) or f.startswith(sanitized_id))

def clean_up_temp_files(id):
	created_files = get_created_files(id)
	for file in created_files:
		os.unlink(file)
