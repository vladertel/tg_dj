from downloader.MasterDownloader import MasterDownloader

mas_downld = MasterDownloader()
# mas_downld.input_queue.put({
# 		"action":"download",
# 		"text":"включи этот клипhttps://www.youtube.com/watch?v=dQw4w9WgXcQ",
# 		"user":"me"
# 	})
# try:
# 	while True:
# 		obj = mas_downld.output_queue.get(timeout=100)
# 		print(obj)
# 		mas_downld.output_queue.task_done()
# except Exception as e:
# 	print("thats all folks!")

mas_downld.input_queue.put({
		"action":"download",
		"text":"sad trombone",
		"user":"me"
	})
try:
	while True:
		obj = mas_downld.output_queue.get(timeout=300)
		print(obj)
		if obj["action"] == "ask_user":
			mas_downld.input_queue.put({
				"action":"user_confirmed",
				"user":"me"
			})
		mas_downld.output_queue.task_done()
except Exception as e:
	print("thats all folks!")