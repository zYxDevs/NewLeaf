import os
import re

def get_created_files(id):
	# youtube-dl transforms filenames when saving, for example changing - to _ at the start to presumbly not trigger switches in shell, but also in other strange ways too
	patterns = [
		"__+", "_",
		"^_*(-_)?", "",
		"^-", "_"
	]
	trim_id = id
	for find, replace in zip(patterns[::-2], patterns[1::-2]): # for each 2 items in the list
		trim_id = re.sub(find, replace, trim_id)

	# all file names then have an underscore before the converted URL
	id += "_"
	trim_id += "_"

	return (f for f in os.listdir() if f.startswith(id) or f.startswith(trim_id))

def clean_up_temp_files(id):
	created_files = get_created_files(id)
	for file in created_files:
		os.unlink(file)
