/* Browser UI: renders the current-standing dashboard and, when a meet PDF is dropped,
 * parses it with pdf.js and renders eligibility + sign-up suggestions. Pure logic lives
 * in app.js (window.SwimLogic); this file only reads the DOM and paints results. */
(function () {
  "use strict";
  var S = window.SwimLogic, DATA = window.SWIM_DATA, STD = window.SWIM_STANDARDS;
  var ORDER = ["B", "BB", "A", "AA", "AAA", "AAAA"];
  var $ = function (sel) { return document.querySelector(sel); };
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]; }); }

  // ---------- dashboard (current standing) ----------
  function gapCell(grp, course, ev, row) {
    var std = STD[grp + "|" + course + "|" + ev];
    var level = row.standard || "<B";
    if (/^slower/i.test(level)) level = "<B";
    if (!std) return [level, "", ""];
    var lvl = ORDER.indexOf(level) >= 0 ? level : "<B";
    var tgt = ORDER.indexOf(lvl) < 0 ? "B"
      : (ORDER.indexOf(lvl) < ORDER.length - 1 ? ORDER[ORDER.indexOf(lvl) + 1] : "");
    if (!tgt || !(tgt in std)) return [level, "", ""];
    return [level, tgt, S.csToStr(row.cs - std[tgt])];
  }

  function renderDashboard() {
    var wrap = $("#dashboard");
    wrap.innerHTML = "";
    DATA.swimmers.forEach(function (sw) {
      wrap.appendChild(el("h3", null, esc(sw.name) + ", age " + sw.age + " (" + esc(sw.ageGroup) + ")"));
      var byCourse = {};
      sw.usasBest.forEach(function (r) { (byCourse[r.course] || (byCourse[r.course] = [])).push(r); });
      ["SCY", "LCM", "SCM"].forEach(function (course) {
        var rows = byCourse[course];
        if (!rows) return;
        rows = rows.slice().sort(function (a, b) { return a.cs - b.cs; });
        var t = el("table");
        t.appendChild(el("caption", null, course));
        t.innerHTML += "<thead><tr><th>Event</th><th>Best</th><th>Level</th><th>Next</th><th>Need</th><th>Date</th></tr></thead>";
        var tb = el("tbody");
        rows.forEach(function (r) {
          var g = gapCell(sw.ageGroup, course, r.event, r);
          tb.appendChild(el("tr", null,
            "<td>" + esc(r.event) + "</td><td>" + esc(r.time) + "</td><td>" + esc(g[0]) +
            "</td><td>" + esc(g[1]) + "</td><td>" + esc(g[2]) + "</td><td>" + esc(r.date) + "</td>"));
        });
        t.appendChild(tb);
        wrap.appendChild(t);
      });
      if (sw.nvslBest && sw.nvslBest.length) {
        var t2 = el("table");
        t2.appendChild(el("caption", null, "NVSL (McLean Marlins, 25 m summer)"));
        t2.innerHTML += "<thead><tr><th>Event</th><th>Best</th><th>Date</th><th>Meet</th></tr></thead>";
        var tb2 = el("tbody");
        sw.nvslBest.slice().sort(function (a, b) { return a.cs - b.cs; }).forEach(function (r) {
          tb2.appendChild(el("tr", null, "<td>" + esc(r.event) + "</td><td>" + esc(r.time) +
            "</td><td>" + esc(r.date) + "</td><td>" + esc(r.meet) + "</td>"));
        });
        t2.appendChild(tb2);
        wrap.appendChild(t2);
      }
    });
    $("#pulled").textContent = "Times last refreshed " + (window.SWIM_PULLED_AT || DATA.pulledAt) +
      ". To update, run “Check a swim meet” or code/swim_data.py.";
  }

  // ---------- meet result ----------
  function renderResult(res) {
    var out = $("#result");
    out.innerHTML = "";
    var sub = res.type === "qualify"
      ? "Qualifying meet — must equal or better a listed standard (LCM or SCY)."
      : "Open meet — no cuts. Lineup balances closeness to the next level against stale PBs.";
    out.appendChild(el("h2", null, esc(res.meet)));
    out.appendChild(el("p", "muted", esc(res.course) + " · " + esc(res.startDate || "date n/a") + " · " + sub));

    res.swimmers.forEach(function (sw) {
      var card = el("div", "swimmer-card");
      card.appendChild(el("h3", null, esc(sw.name) + " (" + esc(sw.ageGroup) + ")"));
      if (!sw.hasEvents) {
        card.appendChild(el("p", "muted", "No events for his age group in this meet."));
        out.appendChild(card); return;
      }
      if (res.type === "qualify") renderQualify(card, sw);
      else renderOpen(card, sw, res.maxEvents);
      out.appendChild(card);
    });
    var note = el("p", "muted foot",
      "PB age is time since the personal best, not since the event was last raced (the " +
      "public USA Swimming API gives best times per course, not full history). NVSL " +
      "summer swims carry full history.");
    out.appendChild(note);
    out.scrollIntoView({behavior: "smooth"});
  }

  function renderQualify(card, sw) {
    if (sw.enter.length) {
      var total = sw.enter.length + (sw.bonus ? sw.bonus.length : 0);
      card.appendChild(el("div", "suggest ok",
        "<strong>Sign up for " + total + ":</strong> qualified: " + esc(sw.enter.join(", ")) +
        (sw.bonus && sw.bonus.length
          ? ". <strong>Bonus (no cut needed): " + esc(sw.bonus.join(", ")) + "</strong>"
          : "") + ". <span class='muted'>Qualifying is banked, so enter every qualified event" +
        (sw.bonus && sw.bonus.length
          ? "; because he qualifies for one, the meet allows up to " + sw.bonusAllow +
            " bonus events, filled here with his closest unqualified events"
          : "") + (sw.cap ? " (meet cap " + sw.cap + ")" : "") + ".</span>"));
    } else {
      card.appendChild(el("div", "suggest none",
        "<strong>No qualifying times yet.</strong> " +
        (sw.near.length ? "Closest: " + esc(sw.near[0].event) + " (" + esc(sw.near[0].row.time) +
          "), " + S.csToStr(sw.near[0].off) + " over the " + sw.near[0].course + " cut." : "")));
    }
    if (sw.chase && sw.chase.length && sw.chase[0].off <= 200) {
      card.appendChild(el("p", "chase", "Worth chasing before entries close: <strong>" +
        esc(sw.chase[0].event) + "</strong> is only " + S.csToStr(sw.chase[0].off) +
        " over the " + sw.chase[0].course + " cut."));
    }
    if (sw.qual.length) {
      var t = el("table");
      t.innerHTML = "<thead><tr><th>Qualified event</th><th>By</th><th>His time</th><th>Standard</th><th>Under by</th></tr></thead>";
      var tb = el("tbody");
      sw.qual.forEach(function (q) {
        tb.appendChild(el("tr", "q-yes", "<td>" + esc(q.event) + "</td><td>" + q.course +
          "</td><td>" + esc(q.row.time) + "</td><td>" + S.csToStr(q.std) + "</td><td>" +
          S.csToStr(q.under) + "</td>"));
      });
      t.appendChild(tb); card.appendChild(t);
    }
    if (sw.near.length) {
      card.appendChild(el("p", "muted", "Closest near-misses:"));
      var t2 = el("table");
      t2.innerHTML = "<thead><tr><th>Event</th><th>Course</th><th>His time</th><th>Standard</th><th>Off by</th></tr></thead>";
      var tb2 = el("tbody");
      sw.near.forEach(function (n) {
        tb2.appendChild(el("tr", null, "<td>" + esc(n.event) + "</td><td>" + n.course +
          "</td><td>" + esc(n.row.time) + "</td><td>" + S.csToStr(n.std) + "</td><td>" +
          S.csToStr(n.off) + "</td>"));
      });
      t2.appendChild(tb2); card.appendChild(t2);
    }
  }

  function renderOpen(card, sw, maxEv) {
    if (sw.picks.length) {
      var pick = sw.picks.map(function (p) {
        return "<strong>" + esc(p.event) + "</strong>" +
          (p === sw.explore && p.pct > S.STRETCH ? " (re-test, PB " + Math.floor(p.days / 30) +
            " mo old)" : " (drop " + S.csToStr(p.need) + " for " + p.next + ")");
      }).join(", ");
      card.appendChild(el("div", "suggest ok", "<strong>Sign up for " + sw.picks.length +
        ":</strong> " + pick + "."));
    } else {
      card.appendChild(el("div", "suggest none", "No timed event with a reachable next cut."));
    }
    var t = el("table");
    t.innerHTML = "<thead><tr><th>Event</th><th>Best</th><th>Level</th><th>Next</th><th>Need</th><th>Need%</th><th>PB age</th><th>Value</th></tr></thead>";
    var tb = el("tbody");
    sw.rows.forEach(function (r) {
      var pb = r.here ? r.here.time : (r.other ? "NT (best " + r.other.time + " " + r.other.course + ")" : "NT");
      var age = r.days == null ? "" : Math.floor(r.days / 30) + " mo" + (r.stale ? "*" : "");
      var value, cls = "";
      if (r.pct == null) value = r.here ? "no next-cut target" : "no time in this course";
      else if (r.pct <= S.GOOD) { value = "TARGET"; cls = "v-target"; }
      else if (r.pct <= S.STRETCH) value = "stretch" + (r.stale ? " + stale" : "");
      else { value = r.stale ? "RE-TEST (PB stale)" : "low value"; cls = r.stale ? "v-retest" : ""; }
      var isPick = sw.picks.indexOf(r) >= 0;
      tb.appendChild(el("tr", (isPick ? "picked " : "") + cls,
        "<td>" + esc(r.event) + "</td><td>" + esc(pb) + "</td><td>" + esc(r.level) +
        "</td><td>" + esc(r.next) + "</td><td>" + (r.need ? S.csToStr(r.need) : "") +
        "</td><td>" + (r.pct ? r.pct.toFixed(1) + "%" : "") + "</td><td>" + age +
        "</td><td>" + esc(value) + "</td>"));
    });
    t.appendChild(tb); card.appendChild(t);
    if (sw.blind.length) card.appendChild(el("p", "muted",
      "Blind options (no time in this course, your call): " +
      sw.blind.map(function (r) { return esc(r.event); }).join(", ") + "."));
  }

  // ---------- PDF -> text (layout reconstruction) ----------
  function pdfToText(buf) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
    return window.pdfjsLib.getDocument({data: buf}).promise.then(function (pdf) {
      var pages = [];
      for (var i = 1; i <= pdf.numPages; i++) pages.push(i);
      return Promise.all(pages.map(function (n) {
        return pdf.getPage(n).then(function (p) { return p.getTextContent(); })
          .then(function (tc) { return pageLines(tc); });
      })).then(function (all) { return all.join("\n"); });
    });
  }
  function pageLines(tc) {
    var items = tc.items.map(function (it) {
      return {x: it.transform[4], y: it.transform[5], s: it.str,
              w: it.width || 0, h: it.height || 8};
    }).filter(function (it) { return it.s.trim() !== ""; });
    // Cluster into visual rows: same line if baselines are within ~half a line height.
    items.sort(function (a, b) { return b.y - a.y || a.x - b.x; });
    var lines = [], cur = [], lastY = null;
    items.forEach(function (it) {
      if (lastY !== null && Math.abs(it.y - lastY) > Math.max(4, it.h * 0.6)) {
        lines.push(flush(cur)); cur = [];
      }
      cur.push(it); lastY = it.y;
    });
    if (cur.length) lines.push(flush(cur));
    return lines.join("\n");
  }
  // Rebuild a pdftotext-layout-like line: concatenate adjacent glyphs, and insert spaces
  // proportional to the horizontal gap so column separations survive (a blanket single
  // space would both split numbers like "2026" and merge separate columns).
  function flush(items) {
    items.sort(function (a, b) { return a.x - b.x; });
    var s = "", prevEnd = null, prevH = 8;
    items.forEach(function (it) {
      if (prevEnd !== null) {
        var gap = it.x - prevEnd, h = prevH || 8;
        // A word space is ~0.25 of the font height; glue anything tighter (keeps "2026"
        // intact), and widen big column gaps into multiple spaces (like pdftotext -layout).
        if (gap > 0.18 * h) s += new Array(Math.max(1, Math.round(gap / (0.45 * h))) + 1).join(" ");
      }
      s += it.s; prevEnd = it.x + it.w; prevH = it.h;
    });
    return s;
  }

  // ---------- wiring ----------
  function runBuffer(buf, label) {
    var status = $("#status");
    status.textContent = "Reading " + (label || "PDF") + " …";
    return pdfToText(buf).then(function (text) {
      var spec = S.toSpec(text);
      if (!Object.keys(spec.events).length) {
        status.textContent = "Could not find age-group events in this PDF. Is it a PVS meet sheet?";
        return;
      }
      status.textContent = "";
      renderResult(S.analyze(spec, DATA, STD));
    });
  }
  function handleFile(file) {
    file.arrayBuffer().then(function (b) { return runBuffer(b, file.name); })
      .catch(function (e) { $("#status").textContent = "Could not read that PDF: " + e.message; });
  }
  function handleUrl(url) {
    var status = $("#status");
    status.textContent = "Fetching the PDF …";
    fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.arrayBuffer();
    }).then(function (b) { return runBuffer(b, url); })
      .catch(function (e) {
        status.textContent = "Could not fetch that link (" + e.message +
          "). Many meet sites block cross-site downloads; save the PDF and drop it here instead.";
      });
  }

  function init() {
    renderDashboard();
    var input = $("#pdf-input"), drop = $("#drop");
    input.addEventListener("change", function () { if (input.files[0]) handleFile(input.files[0]); });
    ["dragover", "dragenter"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) {
      var f = e.dataTransfer.files[0];
      if (f && f.name.toLowerCase().endsWith(".pdf")) handleFile(f);
    });
    var urlInput = $("#pdf-url");
    $("#pdf-url-go").addEventListener("click", function () {
      if (urlInput.value.trim()) handleUrl(urlInput.value.trim());
    });
    urlInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && urlInput.value.trim()) handleUrl(urlInput.value.trim());
    });
  }
  document.addEventListener("DOMContentLoaded", init);
})();
