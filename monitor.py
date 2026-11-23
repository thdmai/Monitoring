import os, re, json, time, pathlib, requests

CONFIG = pathlib.Path(os.getenv("CONFIG", "/config/config.json"))
SEEN = pathlib.Path("/data/seen.json")
H = {"User-Agent": "Mozilla/5.0"}
BASE = "https://trouverunlogement.lescrous.fr/tools/48/accommodations/"

seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()


def send_discord(v, ville, link):
    msg = f"{v.get('mention', '')} Nouveau logement à {ville} : {link}".strip()
    return requests.post(v["webhook"], json={"content": msg}, timeout=15).ok


def send_ntfy(topic, ville, link):
    return requests.post(
        f"https://ntfy.sh/{topic}",
        data=f"Nouveau logement à {ville}".encode(),
        headers={"Title": "Logement CROUS", "Click": link, "Priority": "high"},
        timeout=15,
    ).ok


while True:
    cfg = json.loads(CONFIG.read_text())
    for ville, v in cfg["villes"].items():
        try:
            html = requests.get(v["url"], headers=H, timeout=15).text
        except requests.RequestException as e:
            print("erreur", ville, e, flush=True)
            continue
        if "Aucun logement trouvé" not in html:
            for i in set(re.findall(r"/tools/48/accommodations/(\d+)", html)):
                link = BASE + i
                # (identifiant de destination, fonction d'envoi)
                dests = []
                if v.get("webhook"):
                    dests.append(("discord", lambda: send_discord(v, ville, link)))
                for t in v.get("ntfy", []):
                    dests.append((f"ntfy:{t}", lambda t=t: send_ntfy(t, ville, link)))
                for dest, send in dests:
                    key = f"{ville}|{i}|{dest}"
                    if key in seen:
                        continue
                    try:
                        ok = send()
                    except requests.RequestException as e:
                        print("erreur envoi", ville, dest, e, flush=True)
                        continue
                    if ok:  # marqué comme vu seulement si l'envoi a réussi
                        seen.add(key)
                        print("alerte", ville, i, dest, flush=True)
                    else:
                        print("echec envoi", ville, dest, flush=True)
        time.sleep(2)
    SEEN.write_text(json.dumps(sorted(seen)))
    time.sleep(cfg.get("interval", 300))