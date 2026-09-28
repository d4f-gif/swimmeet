#!/usr/bin/env python3
"""Regenerate swim-data.js for the swim website: pull Ethan & Lucas's latest times from
the USA Swimming official API and NVSL, embed the motivational standards (standards.json),
and write swim-data.js. Runs in GitHub Actions (see .github/workflows/refresh.yml) so the
published site stays current with no local machine, no tokens, no AI. Stdlib only.
Mirrors the swimming-team pipeline in the private vault; keep the two in sync.
"""
import datetime, json, re, time, urllib.error, urllib.request
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


def http(url, body=None, headers=None, tries=3):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
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


def previous_data():
    m = re.search(r"^window\.SWIM_DATA = (.*);$", (HERE / "swim-data.js").read_text(), re.M)
    return json.loads(m.group(1))


def main():
    standards = json.loads((HERE / "standards.json").read_text())
    today = datetime.date.today().isoformat()
    names = {s["name"] for s in SWIMMERS}
    nvsl = nvsl_best(names)
    prev = previous_data()
    prev_by_id = {p["memberId"]: p for p in prev["swimmers"]}
    data = {"pulledAt": today, "usasAsOf": today, "swimmers": []}
    for s in SWIMMERS:
        try:
            rows, age = pull_usas(s)
        except urllib.error.HTTPError as e:
            # USA Swimming closed anonymous per-swimmer access (403 since 2026-08-26): keep the last pulled times.
            if e.code not in (401, 403):
                raise
            old = prev_by_id[s["memberId"]]
            rows, age = old["usasBest"], old["age"]
            data["usasAsOf"] = prev.get("usasAsOf", prev["pulledAt"])
            print(f"USA Swimming returned {e.code} for {s['name']}; kept times as of {data['usasAsOf']}")
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
