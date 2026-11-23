import os, re, json, time, pathlib, requests

CONFIG = pathlib.Path(os.getenv("CONFIG", "/config/config.json"))
SEEN = pathlib.Path("/data/seen.json")
H = {"User-Agent": "Mozilla/5.0"}
BASE = "https://trouverunlogement.lescrous.fr/tools/48/accommodations/"

seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()

while True:
    cfg = json.loads(CONFIG.read_text())  # rechargé à chaque tour : pas de redémarrage pour modifier
    pages = {}  # une seule requête par URL, même si plusieurs personnes la partagent
    for w in cfg["watchers"]:
        for ville, url in w["villes"].items():
            if url not in pages:
                try:
                    pages[url] = requests.get(url, headers=H, timeout=15).text
                except requests.RequestException as e:
                    print("erreur", ville, e, flush=True)
                    pages[url] = None
                time.sleep(2)
            html = pages[url]
            if not html or "Aucun logement trouvé" in html:
                continue
            for i in set(re.findall(r"/tools/48/accommodations/(\d+)", html)):
                key = f"{w['topic']}|{ville}|{i}"
                if key in seen:
                    continue
                seen.add(key)
                link = BASE + i
                requests.post(
                    f"https://ntfy.sh/{w['topic']}",
                    data=f"Nouveau logement à {ville}".encode(),
                    headers={"Title": "Logement CROUS", "Click": link, "Priority": "high"},
                )
                print("alerte", w["name"], ville, i, flush=True)
    SEEN.write_text(json.dumps(sorted(seen)))
    time.sleep(cfg.get("interval", 300))