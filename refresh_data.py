#!/usr/bin/env python3
"""Regenerate swim-data.js for the swim website: pull Ethan & Lucas's latest times from
the USA Swimming official API (login-only since 2026-08-26, so newer swims come from Potomac
Valley Swimming's public Hy-Tek result files) and NVSL, embed the motivational standards (standards.json),
and write swim-data.js. Runs in GitHub Actions (see .github/workflows/refresh.yml) so the
published site stays current with no local machine, no tokens, no AI. Stdlib only.
Mirrors the swimming-team pipeline in the private vault; keep the two in sync.
"""
import datetime, io, json, re, time, urllib.error, urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
API_HDRS = {"AppName": "DataHub", "Usas-Sub-Id": "Anonymous",
            "Device-Id": "cGxhdGZvcm0gLSBcGxhd2ZW5kb3IgLSB1bmtub3duIC0gMTc1MTcyNDAwMDAwMA==",
            "Content-Type": "application/json", "User-Agent": UA}
SWIMMERS = [{"name": "Ethan Hu", "memberId": "CC769BD9092040"},
            {"name": "Lucas Hu", "memberId": "5BBB4ECA30F546"}]
STROKE = {"FR": "Free", "BK": "Back", "BR": "Breast", "FL": "Fly", "IM": "IM"}
NVSL_YEARS = list(range(2025, datetime.date.today().year + 1))
USAS_FROZEN_AT = "2026-08-25"  # last day the anonymous USA Swimming API answered
PVS_BASE = "https://www.files.pvswim.org"
PVS_STROKE = {"1": "Free", "2": "Back", "3": "Breast", "4": "Fly", "5": "IM"}
PVS_COURSE = {"Y": "SCY", "S": "SCM", "L": "LCM", "2": "SCY", "1": "SCM", "3": "LCM"}


def http(url, body=None, headers=None, tries=3, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read() if raw else r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


def t2cs(s):
    s = s.strip()
    if ":" in s:
        m, r = s.split(":")
        return int(m) * 6000 + int(round(float(r) * 100))
    return int(round(float(s) * 100))


def iso(d):
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return d


def age_group(age):
    return ("10 & Under" if age <= 10 else "11-12" if age <= 12
            else "13-14" if age <= 14 else "15-16")


def pull_usas(sw):
    base = "https://times-api.usaswimming.org/swims/TimesSearch"
    events = json.loads(http(f"{base}/GetBestTimesForMember/{sw['memberId']}", headers=API_HDRS))
    combos = sorted({(e["distance"], e["strokeAbbreviation"]) for e in events})
    rows, age = [], None
    for dist, stroke in combos:
        time.sleep(1.0)
        recs = json.loads(http(f"{base}/BestTimes", headers=API_HDRS,
                               body={"memberId": sw["memberId"], "distance": dist,
                                     "strokeAbbreviation": stroke}))
        for r in recs:
            age = max(age or 0, r["swimmerAge"])
            rows.append({"event": f"{dist} {STROKE[stroke]}", "course": r["courseCode"],
                         "time": r["swimTime"], "cs": t2cs(r["swimTime"]),
                         "standard": r.get("timeStandard"), "date": iso(r["swimDate"]),
                         "meet": r["meetName"], "ageAtSwim": r["swimmerAge"]})
    return rows, age


def nvsl_best(wanted):
    ids = set()
    for y in NVSL_YEARS:
        try:
            html = http(f"https://www.mynvsl.com/team-schedules/mclean?year={y}")
            ids |= set(re.findall(r'href="/results/(\d+)', html))
            time.sleep(1.0)
        except Exception:
            pass
    best = {n: {} for n in wanted}
    for mid in sorted(ids):
        try:
            html = http(f"https://www.mynvsl.com/results/{mid}")
        except Exception:
            continue
        time.sleep(1.0)
        title = re.search(r"<h2[^>]*>\s*([^<]+?)\s*</h2>", html)
        date = re.search(r"Date:\s*(?:</[^>]+>|<[^>]+>|\s)*([A-Z][a-z]+ \d{1,2}, \d{4})", html)
        meet = title.group(1).strip() if title else "NVSL meet"
        when = iso(date.group(1)) if date else ""
        for tbl in re.finditer(r"<table>(.*?)</table>", html, re.S):
            head = re.search(r"<th[^>]*>\s*(Boys|Girls)\s+([A-Za-z ]+?)\s+(\d+)M\s+([^<]+?)\s*</th>",
                             tbl.group(1))
            if not head or "Relay" in head.group(2):
                continue
            stroke, dist = head.group(2).strip(), head.group(3)
            for row in re.finditer(r"<tr[^>]*>\s*<td>[^<]*</td>\s*<td>([\d:.]+)</td>\s*"
                                   r"<td>[A-Z]+</td>\s*<td>\s*([^<]+?)\s*</td>", tbl.group(1)):
                t, name = row.groups()
                if name in wanted:
                    ev = f"{dist} {stroke}"
                    cur = best[name].get(ev)
                    if not cur or t2cs(t) < cur["cs"]:
                        best[name][ev] = {"event": ev, "time": t, "cs": t2cs(t),
                                          "date": when, "meet": meet}
    return best


def parse_cl2(text, ids, meet=""):
    """Individual swims (SDIF D0 records) for the given USA Swimming IDs (first 12 chars)."""
    out = []
    for line in text.splitlines():
        if line.startswith("B1") and not meet:
            meet = line[11:41].strip()
        elif line.startswith("D0") and line[39:51].strip() in ids and line[71:72] in PVS_STROKE:
            event = f"{int(line[67:71])} {PVS_STROKE[line[71:72]]}"
            d = line[80:88]
            for t, c in ((line[115:123].strip(), line[123:124]), (line[97:105].strip(), line[105:106])):
                if re.fullmatch(r"(\d+:)?\d+\.\d\d", t) and c in PVS_COURSE:
                    out.append({"memberId": ids[line[39:51].strip()], "event": event,
                                "course": PVS_COURSE[c], "time": t, "cs": t2cs(t),
                                "date": f"{d[4:8]}-{d[0:2]}-{d[2:4]}", "meet": meet,
                                "ageAtSwim": int(line[63:65])})
    return out


def pvs_swims():
    """Swims from Potomac Valley Swimming's public Hy-Tek results; meets already read are cached."""
    cache_path = HERE / "pvs-swims.json"
    cache = (json.loads(cache_path.read_text()) if cache_path.exists()
             else {"meets": [], "swims": []})
    ids = {s["memberId"][:12]: s["memberId"] for s in SWIMMERS}
    today = datetime.date.today()
    start = today.year % 100 - (today.month < 9)  # PVS seasons run Sept-Aug
    pages = [f"{PVS_BASE}/results.html"] + [f"https://www.pvswim.org/results-{y:02d}{y + 1:02d}"
                                           for y in (start - 1, start)]
    zips = set()
    for page in pages:
        zips |= set(re.findall(r'(?:files\.pvswim\.org)?(/\d{4}tm/[^"\\\s]+\.zip)', http(page)))
        time.sleep(1.0)
    for z in sorted(zips - set(cache["meets"])):
        time.sleep(1.0)
        try:
            with zipfile.ZipFile(io.BytesIO(http(PVS_BASE + z, raw=True))) as zf:
                for n in zf.namelist():
                    if n.lower().endswith(".cl2"):
                        full = re.match(r"(?:.*/)?Meet Results-(.+)-\d{1,2}[A-Za-z]{3}\d{4}-\d+\.cl2$", n, re.I)
                        cache["swims"] += parse_cl2(zf.read(n).decode("latin-1"), ids,
                                                    full.group(1) if full else "")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"PVS {z}: skipped this run ({e})")
                continue
        except Exception as e:
            print(f"PVS {z}: skipped this run ({e})")
            continue
        cache["meets"].append(z)
    cache["meets"].sort()
    cache_path.write_text(json.dumps(cache, indent=1) + "\n")
    return cache["swims"]


def level(standards, age, course, event, cs):
    cuts = standards.get(f"{age_group(age)}|{course}|{event}")
    if not cuts:
        return None
    got = "Slower Than B"
    for name, cut in cuts.items():
        if cs <= cut:
            got = name
    return got


def merge_best(rows, swims, standards):
    best = {(r["event"], r["course"]): r for r in rows}
    for s in swims:
        k = (s["event"], s["course"])
        if k not in best or s["cs"] < best[k]["cs"]:
            best[k] = {"event": s["event"], "course": s["course"], "time": s["time"], "cs": s["cs"],
                       "standard": level(standards, s["ageAtSwim"], s["course"], s["event"], s["cs"]),
                       "date": s["date"], "meet": s["meet"], "ageAtSwim": s["ageAtSwim"]}
    return list(best.values())


def previous_data():
    m = re.search(r"^window\.SWIM_DATA = (.*);$", (HERE / "swim-data.js").read_text(), re.M)
    return json.loads(m.group(1))


def main():
    standards = json.loads((HERE / "standards.json").read_text())
    today = datetime.date.today().isoformat()
    names = {s["name"] for s in SWIMMERS}
    nvsl = nvsl_best(names)
    pvs = pvs_swims()
    prev = previous_data()
    prev_by_id = {p["memberId"]: p for p in prev["swimmers"]}
    data = {"pulledAt": today, "swimmers": []}
    for s in SWIMMERS:
        try:
            rows, age = pull_usas(s)
        except urllib.error.HTTPError as e:
            # USA Swimming closed anonymous per-swimmer access (403 since 2026-08-26): keep the
            # last API times and add newer swims from PVS results.
            if e.code not in (401, 403):
                raise
            old = prev_by_id[s["memberId"]]
            rows, age = old["usasBest"], old["age"]
            data["usasNote"] = (f"USA Swimming now requires a login, so USA Swimming times after "
                                f"{USAS_FROZEN_AT} come from Potomac Valley Swimming's public meet results.")
            print(f"USA Swimming returned {e.code} for {s['name']}; using saved times + PVS results")
        mine = [p for p in pvs if p["memberId"] == s["memberId"] and p["date"] > USAS_FROZEN_AT]
        rows = merge_best(rows, mine, standards)
        age = max([age] + [p["ageAtSwim"] for p in mine])
        nb = sorted(nvsl.get(s["name"], {}).values(), key=lambda r: r["cs"])
        data["swimmers"].append({"name": s["name"], "memberId": s["memberId"], "age": age,
                                 "ageGroup": age_group(age), "usasBest": rows,
                                 "nvslSwims": nb, "nvslBest": nb})
    (HERE / "swim-data.js").write_text(
        "window.SWIM_DATA = " + json.dumps(data) + ";\n"
        "window.SWIM_STANDARDS = " + json.dumps(standards) + ";\n"
        f"window.SWIM_PULLED_AT = {json.dumps(today)};\n")
    print(f"wrote swim-data.js: {len(data['swimmers'])} swimmers, pulled {today}")


if __name__ == "__main__":
    main()
