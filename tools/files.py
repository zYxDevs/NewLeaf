import os

def get_created_files(id):
	if id[0] == "-":
		id = "_" + id[1:] # youtube-dl changes - to _ at the start, presumably to not accidentally trigger switches with * in shell
	id += "_"

	# youtube-dl thinks it's a really good idea to do this, for some reason.
	trim_id = id.lstrip("_")
	if trim_id.startswith("-"):
		trim_id = "_" + trim_id[len("-"):]

	return (f for f in os.listdir() if f.startswith(id) or f.startswith(trim_id))

def clean_up_temp_files(id):
	created_files = get_created_files(id)
	for file in created_files:
		os.unlink(file)
