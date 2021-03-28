import os

def get_created_files(id):
	if id[0] == "-":
		id = "_" + id[1:] # youtube-dl changes - to _ at the start, presumably to not accidentally trigger switches with * in shell
	id += "_"
	trim_id = id.lstrip("-_")
	return (f for f in os.listdir() if f.startswith(id) or f.startswith(trim_id))

def clean_up_temp_files(id):
	created_files = get_created_files(id)
	for file in created_files:
		os.unlink(file)
