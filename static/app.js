"use strict";
const $ = (s) => document.querySelector(s),
  media = $("#media"),
  canvas = $("#timeline");
const colors = [
  "#088579",
  "#4666c7",
  "#bd6926",
  "#9857ac",
  "#b14d63",
  "#7e8130",
  "#477d98",
  "#847465",
];
let job = null,
  result = null,
  mapping = {},
  corrections = {},
  editSpeaker = null,
  drag = null,
  version = 0,
  pollTimer = null,
  lastCaption = -2;
const fmt = (t) =>
  `${Math.floor(Math.max(0, t) / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(Math.max(0, t) % 60)
    .toString()
    .padStart(2, "0")}`;
const name = (id) => mapping[id]?.name || `話者 ${id + 1}`;
function notice(text, error = false) {
  $("#notice").hidden = !text;
  $("#notice").textContent = text;
  $("#notice").classList.toggle("error", error);
}
async function api(path, options) {
  const r = await fetch(path, options);
  if (!r.ok) {
    let x;
    try {
      x = await r.json();
    } catch {
      x = { detail: `HTTP ${r.status}` };
    }
    throw Error(
      typeof x.detail === "string" ? x.detail : JSON.stringify(x.detail),
    );
  }
  return r.json();
}
function save() {
  if (job)
    localStorage.setItem("diarization-" + job.id, JSON.stringify(mapping));
}
function loadMapping() {
  try {
    mapping = JSON.parse(localStorage.getItem("diarization-" + job.id) || "{}");
  } catch {
    mapping = {};
  }
}
async function refreshHistory() {
  const jobs = await api("/api/jobs");
  const sel = $("#history");
  sel.replaceChildren();
  for (const j of jobs) {
    const o = document.createElement("option");
    o.value = j.id;
    o.textContent = `${j.status === "done" ? "✓ " : ""}${j.name}`;
    sel.append(o);
  }
  if (job) sel.value = job.id;
  return jobs;
}
async function loadJob(id) {
  const request = ++version;
  clearTimeout(pollTimer);
  media.pause();
  job = await api("/api/jobs/" + id);
  if (request !== version) return;
  result = null;
  media.removeAttribute("src");
  media.load();
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  loadMapping();
  $("#filename").textContent = job.name;
  $("#summary").textContent = job.stage;
  $("#history").value = id;
  $("#speakers").replaceChildren();
  $("#transcript").replaceChildren();
  $("#caption").replaceChildren();
  $("#activeLabels").replaceChildren();
  $("#regions").replaceChildren();
  $("#credit").replaceChildren();
  lastCaption = -2;
  setDownloads(false);
  if (job.status !== "done") {
    notice(job.error || job.stage, job.status === "error");
    if (job.status !== "error")
      pollTimer = setTimeout(
        () => loadJob(id).catch((e) => notice(e.message, true)),
        1500,
      );
    return;
  }
  result = await api(`/api/jobs/${id}/result`);
  if (request !== version) return;
  try {
    corrections = JSON.parse(
      localStorage.getItem("diarization-text-" + job.id) || "{}",
    );
  } catch {
    corrections = {};
  }
  if (result.transcript)
    result.transcript.forEach((r, i) => {
      if (corrections[i] !== undefined) {
        r.original_text = r.text;
        r.text = corrections[i];
        r.edited = true;
      }
    });
  notice([job.asr_error, job.preview_error].filter(Boolean).join(" "));
  $("#summary").textContent =
    `${fmt(result.duration)} · ${result.speakers.length} 話者 · ${result.transcript ? "文字起こし済み" : "話者推定済み"}`;
  media.src = `/api/jobs/${id}/media`;
  $("#player").classList.toggle("audio", !job.has_video);
  $("#audioPlaceholder").hidden = job.has_video;
  $("#seek").max = result.duration;
  $("#seek").value = 0;
  renderSpeakers();
  renderTranscript();
  $("#credit").textContent =
    "このファイルは実行中のサーバー内で処理・保存されます。";
  setDownloads(true);
  updateFrame();
  window.appReady = true;
}
function setDownloads(ready) {
  $("#json").disabled = !ready;
  $("#txt").disabled = !ready || !result?.transcript;
  $("#srt").disabled = !ready || !result?.transcript;
}
function renderSpeakers() {
  const box = $("#speakers");
  box.replaceChildren();
  for (const id of result.speakers) {
    const card = document.createElement("div");
    card.className = "speaker";
    card.id = "speaker-" + id;
    card.style.setProperty("--color", colors[id]);
    const top = document.createElement("div");
    top.className = "speaker-top";
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.textContent = id + 1;
    const input = document.createElement("input");
    input.value = name(id);
    input.maxLength = 30;
    input.setAttribute("aria-label", `話者${id + 1}の表示名`);
    input.oninput = () => {
      mapping[id] = { ...mapping[id], name: input.value };
      save();
      renderTranscript();
      lastCaption = -2;
    };
    const button = document.createElement("button");
    button.textContent = "枠を指定";
    button.disabled = !job.has_video;
    button.onclick = () => {
      editSpeaker = id;
      media.pause();
      $("#regions").classList.add("editing");
      $("#regionHint").hidden = false;
    };
    top.append(dot, input, button);
    const bar = document.createElement("div");
    bar.className = "scorebar";
    bar.append(document.createElement("div"));
    const bottom = document.createElement("div");
    bottom.className = "speaker-bottom";
    bottom.innerHTML =
      '<span class="state">待機</span><span class="value">発話スコア</span>';
    card.append(top, bar, bottom);
    box.append(card);
  }
}
function renderTranscript() {
  lastCaption = -2;
  const box = $("#transcript");
  box.replaceChildren();
  if (!result.transcript) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent =
      "文字起こしは未実行です。「日本語を文字起こし」を有効にしてファイルを開いてください。";
    box.append(p);
    return;
  }
  for (const [i, row] of result.transcript.entries()) {
    const el = document.createElement("div");
    el.className = "utterance";
    el.id = "line-" + i;
    el.style.setProperty("--speaker-color", colors[row.speaker] || "#65747a");
    const t = document.createElement("time");
    t.textContent = fmt(row.start);
    const who = document.createElement("strong");
    who.textContent = row.speaker === null ? "話者不明" : name(row.speaker);
    who.style.color = colors[row.speaker] || "#758083";
    const words = document.createElement("span");
    words.textContent = row.text;
    if (row.uncertain) {
      const u = document.createElement("span");
      u.className = "uncertain";
      u.textContent = "要確認";
      words.append(u);
    }
    const edit = document.createElement("button");
    edit.className = "edit-text";
    edit.textContent = "編集";
    edit.onclick = (e) => {
      e.stopPropagation();
      media.pause();
      const area = document.createElement("textarea");
      area.className = "transcript-edit";
      area.value = row.text;
      area.onclick = (e) => e.stopPropagation();
      words.replaceChildren(area);
      area.focus();
      area.onblur = () => {
        if (area.value !== row.text) {
          row.original_text = row.original_text || row.text;
          row.text = area.value;
          row.edited = true;
          corrections[i] = area.value;
          localStorage.setItem(
            "diarization-text-" + job.id,
            JSON.stringify(corrections),
          );
          lastCaption = -2;
        }
        renderTranscript();
        updateFrame();
      };
    };
    words.append(edit);
    if (row.edited) {
      const flag = document.createElement("span");
      flag.className = "edited";
      flag.textContent = "編集済み";
      words.append(flag);
    }
    el.append(t, who, words);
    el.onclick = () => {
      media.currentTime = row.start;
      media.play().catch(() => {});
    };
    box.append(el);
  }
}
function svg(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
function drawRegions(active) {
  const layer = $("#regions");
  if (drag) return;
  layer.replaceChildren();
  for (const id of result?.speakers || []) {
    const b = mapping[id]?.box;
    if (!b) continue;
    const on = active.includes(id);
    layer.append(
      svg("rect", {
        x: b.x * 1000,
        y: b.y * 562.5,
        width: b.w * 1000,
        height: b.h * 562.5,
        rx: 5,
        fill: "none",
        stroke: colors[id],
        "stroke-width": on ? 4 : 1,
        opacity: on ? 1 : 0.3,
      }),
    );
    if (on) {
      const text = svg("text", {
        x: b.x * 1000 + 6,
        y: Math.max(18, b.y * 562.5 - 5),
        fill: colors[id],
        "font-size": 17,
        "font-weight": 700,
        "paint-order": "stroke",
        stroke: "#101820",
        "stroke-width": 3,
      });
      text.textContent = name(id);
      layer.append(text);
    }
  }
}
function followTranscript(line, instant = false) {
  const box = $("#transcript");
  if (
    !line ||
    !$("#followTranscript").checked ||
    !box.clientHeight ||
    box.querySelector("textarea")
  )
    return;
  const b = box.getBoundingClientRect(),
    r = line.getBoundingClientRect();
  if (r.top < b.top + 12 || r.bottom > b.bottom - 12) {
    box.scrollTo({
      top: box.scrollTop + r.top - b.top - (box.clientHeight - r.height) / 2,
      behavior:
        instant || matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
    });
  }
}
$("#followTranscript").onchange = () =>
  followTranscript(document.querySelector(".utterance.current"), true);
function updateFrame() {
  if (!result) return;
  const t = media.currentTime || 0;
  const active = [
    ...new Set(
      result.segments
        .filter((s) => s.start <= t && s.end > t)
        .map((s) => s.speaker),
    ),
  ];
  const probs =
    result.probabilities[
      Math.min(
        result.probabilities.length - 1,
        Math.floor(t / result.probability_step),
      )
    ] || [];
  $("#clock").textContent = `${fmt(t)} / ${fmt(result.duration)}`;
  $("#sourceClock").textContent = ` ${fmt(t)}`;
  $("#seek").value = t;
  for (const id of result.speakers) {
    const card = $("#speaker-" + id),
      on = active.includes(id);
    card.classList.toggle("on", on);
    card.querySelector(".scorebar div").style.width =
      `${Math.max(0, Math.min(1, probs[id] || 0)) * 100}%`;
    card.querySelector(".state").textContent = on ? "発話中" : "待機";
    card.querySelector(".value").textContent =
      `発話スコア ${Math.round((probs[id] || 0) * 100)}`;
  }
  const labels = $("#activeLabels");
  labels.replaceChildren();
  for (const id of active) {
    const span = document.createElement("span");
    span.className = "active-label";
    span.style.background = colors[id];
    span.textContent = name(id);
    labels.append(span);
  }
  const ci =
    result.transcript?.findIndex((s) => s.start <= t && s.end > t) ?? -1;
  if (ci !== lastCaption) {
    $("#caption").replaceChildren();
    document.querySelectorAll(".utterance.current").forEach((e) => {
      e.classList.remove("current");
      e.removeAttribute("aria-current");
    });
    if (ci >= 0) {
      const row = result.transcript[ci],
        span = document.createElement("span");
      span.textContent = row.text;
      $("#caption").append(span);
      const line = $("#line-" + ci);
      if (line) {
        line.classList.add("current");
        line.setAttribute("aria-current", "true");
        followTranscript(line, media.seeking || media.paused);
      }
    }
    lastCaption = ci;
  }
  drawRegions(active);
  drawTimeline(t);
}
function drawTimeline(t) {
  const rect = canvas.getBoundingClientRect(),
    dpr = devicePixelRatio || 1,
    w = Math.round(rect.width * dpr),
    h = Math.round(rect.height * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const c = canvas.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = rect.width,
    H = rect.height;
  c.clearRect(0, 0, W, H);
  if (!result) return;
  const left = 95,
    right = 18,
    width = W - left - right;
  const rowH = (H - 35) / Math.max(1, result.speakers.length);
  for (const [i, id] of result.speakers.entries()) {
    const y = 10 + i * rowH;
    c.fillStyle = "#65747a";
    c.font = "12px sans-serif";
    c.fillText(name(id).slice(0, 8), 0, y + rowH * 0.65);
    c.fillStyle = "#f0f1eb";
    c.fillRect(left, y, width, rowH - 9);
    c.fillStyle = colors[id];
    for (const s of result.segments.filter((s) => s.speaker === id)) {
      c.fillRect(
        left + (s.start / result.duration) * width,
        y,
        Math.max(1, ((s.end - s.start) / result.duration) * width),
        rowH - 9,
      );
    }
  }
  c.fillStyle = "#607477";
  c.font = "11px ui-monospace,monospace";
  for (let i = 0; i <= 6; i++) {
    const x = left + (i / 6) * width;
    c.fillText(fmt((i / 6) * result.duration), Math.min(W - 38, x - 15), H - 2);
  }
  const x = left + (t / result.duration) * width;
  c.fillStyle = "#203036";
  c.fillRect(x, 3, 2, H - 25);
  c.beginPath();
  c.moveTo(x - 5, 1);
  c.lineTo(x + 6, 1);
  c.lineTo(x, 8);
  c.fill();
}
canvas.onclick = (e) => {
  if (!result) return;
  const r = canvas.getBoundingClientRect();
  media.currentTime = Math.max(
    0,
    Math.min(
      result.duration,
      ((e.clientX - r.left - 95) / (r.width - 113)) * result.duration,
    ),
  );
  updateFrame();
};
$("#play").onclick = () =>
  media.paused
    ? media.play().catch((e) => notice(e.message, true))
    : media.pause();
media.onplay = () => {
  $("#play").textContent = "Ⅱ";
  $("#play").setAttribute("aria-label", "一時停止");
};
media.onpause = () => {
  $("#play").textContent = "▶";
  $("#play").setAttribute("aria-label", "再生");
};
media.ontimeupdate = updateFrame;
media.onloadedmetadata = updateFrame;
$("#seek").oninput = (e) => {
  media.currentTime = +e.target.value;
  updateFrame();
};
$("#speed").onchange = (e) => (media.playbackRate = +e.target.value);
window.addEventListener("resize", updateFrame);
$("#history").onchange = (e) =>
  loadJob(e.target.value).catch((e) => notice(e.message, true));
$("#file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > 2 * 1024 ** 3) {
    notice("ファイルは2GB以内にしてください。", true);
    return;
  }
  const data = new FormData();
  data.append("file", file);
  data.append("transcribe", $("#asr").checked ? "true" : "false");
  notice("ローカルサーバーへファイルを送っています…");
  try {
    const j = await api("/api/jobs", { method: "POST", body: data });
    await refreshHistory();
    await loadJob(j.id);
  } catch (err) {
    notice(err.message, true);
  } finally {
    e.target.value = "";
  }
};
function download(filename, data, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([data], { type }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
}
$("#json").onclick = () => {
  if (result)
    download(
      "speaker-notes.json",
      JSON.stringify({ ...result, source: job.name, mapping }, null, 2),
      "application/json",
    );
};
const stamp = (t) => {
  const ms = Math.round(t * 1000),
    h = Math.floor(ms / 3600000),
    m = Math.floor(ms / 60000) % 60,
    s = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`;
};
$("#srt").onclick = () => {
  if (result?.transcript)
    download(
      "speaker-notes.srt",
      result.transcript
        .map(
          (s, i) =>
            `${i + 1}\n${stamp(s.start)} --> ${stamp(s.end)}\n${s.speaker === null ? "話者不明" : name(s.speaker)}：${s.text}${s.uncertain ? "［要確認］" : ""}\n`,
        )
        .join("\n"),
      "text/plain;charset=utf-8",
    );
};
$("#txt").onclick = () => {
  if (result?.transcript)
    download(
      "speaker-notes.txt",
      result.transcript
        .map(
          (s) =>
            `[${fmt(s.start)}] ${s.speaker === null ? "話者不明" : name(s.speaker)}：${s.text}${s.uncertain ? "［要確認］" : ""}`,
        )
        .join("\n"),
      "text/plain;charset=utf-8",
    );
};
const layer = $("#regions");
function position(e) {
  const r = layer.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
    y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
  };
}
layer.onpointerdown = (e) => {
  if (editSpeaker === null) return;
  drag = position(e);
  layer.setPointerCapture(e.pointerId);
};
layer.onpointermove = (e) => {
  if (!drag) return;
  const p = position(e);
  layer.replaceChildren(
    svg("rect", {
      x: Math.min(drag.x, p.x) * 1000,
      y: Math.min(drag.y, p.y) * 562.5,
      width: Math.abs(drag.x - p.x) * 1000,
      height: Math.abs(drag.y - p.y) * 562.5,
      fill: "none",
      stroke: colors[editSpeaker],
      "stroke-width": 3,
    }),
  );
};
layer.onpointerup = (e) => {
  if (!drag) return;
  const p = position(e),
    box = {
      x: Math.min(drag.x, p.x),
      y: Math.min(drag.y, p.y),
      w: Math.abs(drag.x - p.x),
      h: Math.abs(drag.y - p.y),
    };
  if (box.w > 0.01 && box.h > 0.01) {
    mapping[editSpeaker] = { ...mapping[editSpeaker], box };
    save();
  }
  cancelRegion();
};
function cancelRegion() {
  drag = null;
  editSpeaker = null;
  layer.classList.remove("editing");
  $("#regionHint").hidden = true;
  updateFrame();
}
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cancelRegion();
});
$("#clearBoxes").onclick = () => {
  for (const k of Object.keys(mapping)) delete mapping[k].box;
  save();
  updateFrame();
};
(async () => {
  try {
    const jobs = await refreshHistory();
    const chosen = jobs[0];
    if (chosen) await loadJob(chosen.id);
    else setDownloads(false);
  } catch (e) {
    notice("サーバーに接続できません。" + e.message, true);
  }
})();
const present = document.createElement("button");
present.textContent = "実演表示";
present.onclick = () => {
  document.body.classList.toggle("demo");
  updateFrame();
};
document.querySelector(".actions").append(present);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.body.classList.remove("demo");
    updateFrame();
  }
});
let playbackFrame;
media.addEventListener("play", () => {
  cancelAnimationFrame(playbackFrame);
  const loop = () => {
    updateFrame();
    if (!media.paused) playbackFrame = requestAnimationFrame(loop);
  };
  loop();
});
