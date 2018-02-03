from user_agent import generate_user_agent
headers = {
	"User-Agent": generate_user_agent(),
	"Accept": "application/json, text/javascript, */*; q=0.01",
	"Pragma": "no-cache",
	"Origin": "https://datmusic.xyz",
	"Referer": "https://datmusic.xyz/",
	"Accept-Language": "en-us"
}
payload = {
	"q":"rick astley",
	"page":0
}
url = "https://api.datmusic.xyz/search"
import requests
import json
result = requests.get(url, params=payload, headers=headers)
data = json.loads(result.text)
print(result.text)
print(data)