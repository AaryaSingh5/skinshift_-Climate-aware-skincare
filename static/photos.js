// Visual photo history. Photos are kept ONLY in this browser (IndexedDB) and are never uploaded.
// The one exception is the optional quality check, which sends a single photo to
// /api/consumer/photo (analysed and discarded) after the user ticks the box for that photo.
// The history makes no measurements or health claims: it shows photos, dates and comparisons.
const DAY = 86400000, FIRST_PAGE = 4;
let sel = [], urls = [], showAll = false, layout = "grid", pending = null, pendingUrl = null, viewing = null, mine = [], who = null;

// ---------- storage (IndexedDB, same schema as before: db "skinshift", store "photos") ----------
let dbp = null;
const idb = () => dbp || (dbp = new Promise((res, rej) => { const r = indexedDB.open("skinshift", 1); r.onupgradeneeded = () => r.result.createObjectStore("photos", {keyPath: "id", autoIncrement: true}); r.onsuccess = () => res(r.result); r.onerror = () => { dbp = null; rej(r.error); }; }));
const tx = async (mode, fn) => { const d = await idb(); return new Promise((res, rej) => { const t = d.transaction("photos", mode), rq = fn(t.objectStore("photos")); t.oncomplete = () => res(rq && rq.result); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error || new Error("Storage is full or unavailable.")); }); };
const owner = async () => who || (who = (await api("/api/consumer/me")).email);
async function savePhoto(blob, day, redness) { const me = await owner(); await tx("readwrite", s => s.add({owner: me, day, redness: redness == null ? null : redness, blob})); }
async function allMine() { const me = await owner(); return (await tx("readonly", s => s.getAll())).filter(p => p.owner === me).sort((a, b) => a.day < b.day ? -1 : a.day > b.day ? 1 : a.id - b.id); }
async function clearPhotos() { for (const p of await allMine()) await tx("readwrite", s => s.delete(p.id)); }

// ---------- helpers ----------
const localDay = (d = new Date()) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const asDate = day => { const [y, m, d] = day.split("-").map(Number); return new Date(y, m - 1, d); };
const pretty = day => asDate(day).toLocaleDateString("en-US", {month: "short", day: "numeric", year: "numeric"});
const daysBetween = (a, b) => Math.round((asDate(b) - asDate(a)) / DAY);
const span = n => n == 0 ? "the same day" : n < 14 ? n + (n == 1 ? " day" : " days") : n < 70 ? Math.round(n / 7) + " weeks" : Math.round(n / 30.4) + " months";
const url = blob => { const u = URL.createObjectURL(blob); urls.push(u); return u; };
const toDataUrl = blob => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsDataURL(blob); });
// Re-encoding through a canvas also drops EXIF data (such as GPS location) from the kept copy.
async function toJpeg(file, max = 1280) { const b = await createImageBitmap(file), s = Math.min(1, max / Math.max(b.width, b.height)), c = document.createElement("canvas");
  c.width = Math.round(b.width * s); c.height = Math.round(b.height * s); c.getContext("2d").drawImage(b, 0, 0, c.width, c.height); if (b.close) b.close();
  return new Promise((res, rej) => c.toBlob(x => x ? res(x) : rej(new Error("That image could not be read.")), "image/jpeg", .85)); }
const openDlg = d => d.showModal ? d.showModal() : d.setAttribute("open", "");
const closeDlg = d => d.close ? d.close() : d.removeAttribute("open");
const say = t => $("#pr").textContent = t;

// ---------- upload flow ----------
$("#pcam").onclick = () => $("#pfc").click();
$("#pgal").onclick = () => $("#pfg").click();
["#pfc", "#pfg"].forEach(id => $(id).onchange = () => { const f = $(id).files[0]; $(id).value = ""; if (f) startSave(f); });
function startSave(f) {
  if (!f.type.startsWith("image/")) { say("Please choose an image file."); return; }
  say(""); pending = f; if (pendingUrl) URL.revokeObjectURL(pendingUrl); pendingUrl = URL.createObjectURL(f); $("#ppv").src = pendingUrl;
  const t = localDay(); $("#pdate").max = t; $("#pdate").value = t; $("#pcn").checked = false; $("#pcn").disabled = false; $("#psnote").textContent = "Saving keeps the photo on this device only. Nothing is uploaded unless you tick the box above."; $("#psave").disabled = false; openDlg($("#psheet")); }
$("#pdate").onchange = () => { const old = $("#pdate").value != localDay(); $("#pcn").disabled = old; if (old) { $("#pcn").checked = false; $("#psnote").textContent = "The quality check is only available for a photo taken today."; } };
$("#pcancel").onclick = () => { pending = null; closeDlg($("#psheet")); };
$("#psheet").addEventListener("close", () => { if (pendingUrl) { URL.revokeObjectURL(pendingUrl); pendingUrl = null; } });
$("#pform").onsubmit = async e => { e.preventDefault(); if (!pending) return; const day = $("#pdate").value; if (!day || day > localDay()) { $("#psnote").textContent = "Choose today or an earlier date."; return; }
  $("#psave").disabled = true; let msg = "", redness = null;
  try {
    const blob = await toJpeg(pending);
    if ($("#pcn").checked) { try { const r = await api("/api/consumer/photo", {body: {image: await toDataUrl(blob), consent_image: true}}); if (r.ok) { redness = r.redness_index; msg = " Quality check: good photo. " + r.stored; } else msg = " Quality check: " + r.issues.join(" ") + " " + r.stored; } catch (x) { msg = " The quality check didn’t run (" + x.message + ")."; } }
    try { await savePhoto(blob, day, redness); } catch { say("Couldn’t keep the photo on this device (private browsing or storage full?)."); closeDlg($("#psheet")); pending = null; return; }
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
    say("Saved to this device for " + pretty(day) + "." + msg); pending = null; closeDlg($("#psheet")); showAll = false; loadPhotos(); loadGallery();
  } catch (x) { $("#psnote").textContent = x.message; $("#psave").disabled = false; } };

// ---------- optional server-side check readings (numbers only) ----------
async function loadPhotos() { const b = $("#ph"); try { const s = await api("/api/consumer/photo/summary"); b.replaceChildren(); add(b, "p", s.summary); s.readings.slice(-8).forEach(r => add(b, "p", r.day + ": " + r.redness, "mu")); add(b, "p", s.note, "mu"); } catch { b.replaceChildren(); } }

// ---------- gallery, timeline, compare ----------
function nextHint() { const h = $("#pnext"); if (!mine.length) { h.textContent = "Your first photo becomes the starting point for your timeline."; return; }
  const n = daysBetween(mine[mine.length - 1].day, localDay()), left = 14 - n; h.textContent = "Last photo: " + (n <= 0 ? "today" : span(n) + " ago") + ". " + (left > 0 ? "A new one is suggested in " + span(left) + "." : "A new photo would be a good idea now."); }
function card(p, cls) { const w = document.createElement("div"); w.className = cls + (sel.includes(p.id) ? " sel" : ""); return w; }
function toggle(p) { sel = sel.includes(p.id) ? sel.filter(x => x !== p.id) : [...sel, p.id].slice(-2); loadGallery(); }
function thumb(p, parent, withDate) { const o = add(parent, "button", "", "open"); o.type = "button"; o.setAttribute("aria-label", "Open photo from " + pretty(p.day)); const im = document.createElement("img"); im.src = url(p.blob); im.alt = "Skin photo from " + pretty(p.day); o.appendChild(im); if (withDate) add(o, "span", pretty(p.day), "dt"); o.onclick = () => view(p); return o; }
function pick(p, parent) { const b = add(parent, "button", "", "pick"); b.type = "button"; b.setAttribute("aria-pressed", sel.includes(p.id)); b.setAttribute("aria-label", "Select photo from " + pretty(p.day) + " for comparison"); b.innerHTML = '<svg class="i"><use href="#i-check"/></svg>'; b.onclick = () => toggle(p); }
async function loadGallery() {
  const g = $("#gal"), t = $("#tl"); let fresh;
  try { fresh = await allMine(); } catch { mine = []; g.replaceChildren(); t.replaceChildren(); $("#cmp").hidden = true; $("#gh").textContent = "Photo history isn’t available in this browser mode."; $("#gsee").hidden = true; nextHint(); return; }
  mine = fresh; urls.forEach(URL.revokeObjectURL); urls = []; g.replaceChildren(); t.replaceChildren(); $("#cmp").hidden = true;
  sel = sel.filter(id => mine.some(p => p.id === id)); nextHint();
  g.hidden = layout != "grid"; t.hidden = layout != "timeline"; $("#vgrid").setAttribute("aria-pressed", layout == "grid"); $("#vtl").setAttribute("aria-pressed", layout == "timeline");
  if (!mine.length) { add(g, "div", "No photos yet. Take or choose one to start your timeline.", "empty"); $("#gsee").hidden = true; $("#gh").textContent = ""; return; }
  $("#gsee").hidden = layout != "grid" || mine.length <= FIRST_PAGE; $("#gsee").firstChild.textContent = showAll ? "Show less" : "See all";
  const recent = [...mine].reverse(), shown = showAll ? recent : recent.slice(0, FIRST_PAGE);
  shown.forEach(p => { const w = card(p, "ph"); thumb(p, w, true); pick(p, w); g.appendChild(w); });
  mine.forEach((p, i) => { const w = card(p, "step"); add(w, "div", pretty(p.day), "when"); add(w, "div", i ? span(daysBetween(mine[i - 1].day, p.day)) + " after the previous photo" : "Starting point", "gap"); thumb(p, w, false); const r = add(w, "div", "", "row"); const b = add(r, "button", sel.includes(p.id) ? "Selected for comparison" : "Select for comparison", "alt"); b.type = "button"; b.setAttribute("aria-pressed", sel.includes(p.id)); b.onclick = () => toggle(p); t.appendChild(w); });
  $("#gh").textContent = sel.length == 1 ? "Select one more photo to compare." : sel.length == 2 ? "" : mine.length < 2 ? "Add a second photo in a few weeks to compare." : "Tick two photos to compare them. Photos are stored only on this device.";
  if (sel.length == 2) compare(mine.filter(p => sel.includes(p.id)));
}
$("#gsee").onclick = () => { showAll = !showAll; loadGallery(); };
$("#vgrid").onclick = () => { layout = "grid"; loadGallery(); };
$("#vtl").onclick = () => { layout = "timeline"; loadGallery(); };

function compare([a, b]) { // already sorted oldest first
  const c = $("#cmp"), ua = url(a.blob), ub = url(b.blob), n = daysBetween(a.day, b.day);
  $("#cbi").src = ua; $("#cai").src = ub; $("#csb").src = ua; $("#csa").src = ub;
  $("#cbi").alt = $("#csb").alt = "Earlier photo from " + pretty(a.day); $("#cai").alt = $("#csa").alt = "Later photo from " + pretty(b.day);
  $("#clb").textContent = "Before · " + pretty(a.day); $("#cla").textContent = "After · " + pretty(b.day); $("#csbl").textContent = "Before · " + pretty(a.day); $("#csal").textContent = "After · " + pretty(b.day);
  $("#cmeta").textContent = n == 0 ? "Both photos are from the same day." : span(n) + " between these photos."; c.hidden = false; reveal();
}
function reveal() { const v = $("#cs").value; $("#cai").style.clipPath = "inset(0 0 0 " + v + "%)"; $("#cbr").style.left = v + "%"; }
$("#cs").oninput = reveal;
$("#cmode").onclick = () => { const side = $("#cside").hidden; $("#cside").hidden = !side; $("#cba").hidden = side; $("#cs").hidden = side; $("#cmode").textContent = side ? "Slide comparison" : "Side by side"; };
$("#cclr").onclick = () => { sel = []; loadGallery(); };

// ---------- single photo view ----------
function view(p) { viewing = p; $("#pv-h").textContent = pretty(p.day); $("#pvi").src = url(p.blob); $("#pvi").alt = "Skin photo from " + pretty(p.day); $("#pvsel").textContent = sel.includes(p.id) ? "Remove from comparison" : "Select for comparison"; openDlg($("#pview")); }
$("#pvx").onclick = () => closeDlg($("#pview"));
$("#pvsel").onclick = () => { closeDlg($("#pview")); toggle(viewing); };
$("#pvdel").onclick = async () => { if (!confirm("Delete this photo from this device?")) return; await tx("readwrite", s => s.delete(viewing.id)); closeDlg($("#pview")); loadGallery(); };
$("#pcl").onclick = async () => { if (confirm("Remove all your kept photos from this device?")) { try { await clearPhotos(); } catch {} sel = []; showAll = false; loadGallery(); } };
