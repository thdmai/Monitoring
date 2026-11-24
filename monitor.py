import os, re, json, time, html as htmllib, pathlib, requests
from urllib.parse import quote
from datetime import datetime, timezone

CONFIG = pathlib.Path(os.getenv("CONFIG", "/config/config.json"))
SEEN = pathlib.Path("/data/seen.json")
H = {"User-Agent": "Mozilla/5.0"}
SITE = "https://trouverunlogement.lescrous.fr"
BASE = SITE + "/tools/48/accommodations/"
LABELS = ["Conditions particulières", "Superficie", "Type de cohabitation", "Loyer",
          "Avance déductible du premier mois de loyer", "Équipements", "Lits", "Description"]

seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()


def clean(raw):
    raw = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", htmllib.unescape(raw)).strip()

def fetch(url):
    r = requests.get(url, headers=H, timeout=15)
    r.encoding = "utf-8"
    return r.text

def get_details(i):
    """Lit la page de l'annonce. Renvoie {} si ça échoue : l'alerte part quand même."""
    try:
        raw = fetch(BASE + i)
        d = {}
        m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
        if m:
            d["titre"] = clean(m.group(1))
        text = clean(raw)
        if d.get("titre"):
            m = re.search(re.escape(d["titre"]) + r" (.+?) Caractéristiques du logement", text)
            if m:
                d["adresse"] = m.group(1)
            if " - " in d["titre"]:
                d["residence"] = d["titre"].split(" - ", 1)[1]
        alt = "|".join(re.escape(x) for x in LABELS)
        for lab in LABELS[:-1]:  # sans la description, trop longue
            m = re.search(rf"{re.escape(lab)} ?: (.+?)(?= (?:{alt}) ?:| Connectez-vous|$)", text)
            if m:
                d[lab] = m.group(1)
        m = re.search(r"(/media/cache/resolve/[^\"'\s>)]+)", raw)
        if m:
            d["image"] = SITE + quote(m.group(1), safe="/%:@")
        return d
    except Exception as e:
        print("erreur détails", i, e, flush=True)
        return {}


def send_discord(v, ville, i, d):
    link = BASE + i
    fields = []
    for name, val in (("Ville", ville), ("Résidence", d.get("residence")),
                      ("Superficie", d.get("Superficie")), ("Type", d.get("Type de cohabitation"))):
        if val:
            fields.append({"name": name, "value": val[:200], "inline": True})
    embed = {
        "description": f"👉 [Cliquez ici pour voir l'annonce]({link})",
        "color": 0x3498DB,
        "fields": fields,
        "footer": {"text": f"Annonce n°{i}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if d.get("image"):
        embed["image"] = {"url": d["image"]}
    content = f"{v.get('mention', '')} 🚨 NOUVEAU LOGEMENT 🚨".strip()
    r = requests.post(v["webhook"], json={"content": content, "embeds": [embed]}, timeout=15)
    if not r.ok and "image" in embed:  # image refusée : on réessaie sans
        del embed["image"]
        r = requests.post(v["webhook"], json={"content": content, "embeds": [embed]}, timeout=15)
    if not r.ok:
        print("discord", r.status_code, r.text[:200], flush=True)
    return r.ok


def send_ntfy(topic, ville, i, d):
    lignes = [d.get("titre", f"Nouveau logement à {ville}")]
    infos = " · ".join(x for x in (d.get("Superficie"), d.get("Loyer")) if x)
    if infos:
        lignes.append(infos)
    return requests.post(
        f"https://ntfy.sh/{topic}",
        data="\n".join(lignes).encode(),
        headers={"Title": f"Logement CROUS - {ville}".encode("utf-8"), "Click": BASE + i, "Priority": "high"},
        timeout=15,
    ).ok


while True:
    cfg = json.loads(CONFIG.read_text())
    for ville, v in cfg["villes"].items():
        try:
            html = fetch(v["url"])
        except requests.RequestException as e:
            print("erreur", ville, e, flush=True)
            continue
        if "Aucun logement trouvé" not in html:
            for i in set(re.findall(r"/tools/48/accommodations/(\d+)", html)):
                dests = (["discord"] if v.get("webhook") else []) + [f"ntfy:{t}" for t in v.get("ntfy", [])]
                pending = [p for p in dests if f"{ville}|{i}|{p}" not in seen]
                if not pending:
                    continue
                d = get_details(i)  # une seule lecture par annonce
                for dest in pending:
                    try:
                        ok = send_discord(v, ville, i, d) if dest == "discord" else send_ntfy(dest[5:], ville, i, d)
                    except requests.RequestException as e:
                        print("erreur envoi", ville, dest, e, flush=True)
                        continue
                    if ok:
                        seen.add(f"{ville}|{i}|{dest}")
                        print("alerte", ville, i, dest, flush=True)
        time.sleep(2)
    SEEN.write_text(json.dumps(sorted(seen)))
    time.sleep(cfg.get("interval", 300))