import requests, json

TOKEN = "sbp_593d5e9ee8bb02f6856c72707d1d8e71523d4f83"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
REF = "bgaggngbxxuycegrjoge"

r = requests.get(
    f"https://api.supabase.com/v1/projects/{REF}/api-keys",
    headers=HEADERS,
    timeout=10,
)

if r.ok:
    keys = r.json()
    for k in keys:
        name = k.get("name", "")
        api_key = k.get("api_key", "")
        if name == "service_role key":
            print(f"SERVICE_KEY={api_key}")
        elif name == "anon key":
            print(f"ANON_KEY={api_key}")
else:
    print(f"Error: {r.status_code} {r.text[:300]}")
