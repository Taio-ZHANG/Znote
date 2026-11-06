const $ = (id) => document.getElementById(id);

const state = {
  module: null,
  note: null,
  savedContent: "",
  searching: false,
  viewMode: "edit",
  sortModes: { modules: "manual", notes: "manual" },
};

marked.setOptions({ breaks: true, gfm: true });

async function api(url, options) {
  const res = await fetch(url, options);
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && data.error) || res.statusText);
  return data;
}

let toastTimer = null;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

function nameFromPath(path) {
  return path.split("/").pop().replace(/\.md$/i, "");
}

function isDirty() {
  return $("note-body").value !== state.savedContent;
}

function updateDirty() {
  const dirty = isDirty();
  $("btn-save").textContent = "保存";
  $("btn-save").classList.toggle("primary", dirty);
  $("save-state").textContent = dirty ? "未保存" : state.note ? "已保存" : "";
  $("save-state").classList.toggle("dirty", dirty);
}

function renderPreview() {
  const html = marked.parse($("note-body").value || "");
  const el = $("note-preview");
  el.innerHTML = html;
  el.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src") || "";
    if (src.startsWith("../attachments/")) {
      img.src = "/files/" + src.replace(/^\.\.\//, "");
    }
  });
}

function setViewMode(mode) {
  state.viewMode = mode === "preview" ? "preview" : "edit";
  const preview = state.viewMode === "preview";
  if (preview) renderPreview();
  $("note-body").hidden = preview;
  $("note-preview").hidden = !preview;
  $("btn-edit-mode").classList.toggle("active", !preview);
  $("btn-preview-mode").classList.toggle("active", preview);
  $("btn-edit-mode").setAttribute("aria-pressed", String(!preview));
  $("btn-preview-mode").setAttribute("aria-pressed", String(preview));
}

function toggleSidebar() {
  const collapsed = $("layout").classList.toggle("sidebar-collapsed");
  const btn = $("btn-toggle-sidebar");
  const label = collapsed ? "展开侧栏" : "收起侧栏";
  btn.setAttribute("aria-expanded", String(!collapsed));
  btn.setAttribute("aria-label", label);
  btn.title = `${label} (Ctrl+B)`;
}

function setActiveNote(path) {
  document.querySelectorAll("#note-list .note-item").forEach((li) => {
    li.classList.toggle("active", li.dataset.path === path);
  });
}

function clearEditor() {
  state.note = null;
  state.savedContent = "";
  $("note-title").value = "";
  $("note-body").value = "";
  renderPreview();
  updateDirty();
}

function renderModules() {
  const ul = $("module-list");
  ul.innerHTML = "";
  const modules = state.modules || [];
  $("module-count").textContent = modules.length ? String(modules.length) : "";
  if (!modules.length) {
    ul.innerHTML = '<li class="empty">暂无模块<br>点击上方 + 新建</li>';
    return;
  }
  modules.forEach((m) => {
    const li = document.createElement("li");
    li.className = "module-item draggable";
    li.draggable = true;
    li.dataset.id = m.name;
    li.title = m.name;
    li.classList.toggle("active", m.name === state.module);
    const span = document.createElement("span");
    span.className = "module-name";
    span.textContent = m.name;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = m.count;
    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "×";
    del.title = `删除模块“${m.name}”`;
    del.setAttribute("aria-label", `删除模块 ${m.name}`);
    del.onclick = (e) => { e.stopPropagation(); deleteModule(m.name); };
    li.append(span, count, del);
    li.onclick = () => selectModule(m.name);
    ul.appendChild(li);
  });
}

function renderNotes(notes) {
  const ul = $("note-list");
  ul.innerHTML = "";
  $("note-count").textContent = notes.length ? String(notes.length) : "";
  if (!notes.length) {
    ul.innerHTML = '<li class="empty">这个模块还没有笔记<br>点击上方“新建”开始记录</li>';
    return;
  }
  notes.forEach((n) => {
    const li = document.createElement("li");
    li.className = "note-item draggable";
    li.draggable = true;
    li.dataset.id = n.path;
    li.dataset.path = n.path;
    const name = document.createElement("div");
    name.className = "note-name";
    name.textContent = nameFromPath(n.path);
    const date = document.createElement("div");
    date.className = "note-date";
    date.textContent = new Date(n.mtime * 1000).toLocaleString();
    li.append(name, date);
    li.onclick = () => openNote(n.path);
    ul.appendChild(li);
  });
  setActiveNote(state.note && state.note.path);
}

function renderSearchResults(results) {
  const ul = $("note-list");
  ul.innerHTML = "";
  $("note-sort").disabled = true;
  $("note-count").textContent = results.length ? String(results.length) : "";
  if (!results.length) {
    ul.innerHTML = '<li class="empty">没有找到匹配的笔记<br>试试其他关键词</li>';
    return;
  }
  results.forEach((r) => {
    const li = document.createElement("li");
    li.className = "note-item";
    li.dataset.path = r.path;
    const name = document.createElement("div");
    name.className = "note-name";
    name.textContent = nameFromPath(r.path);
    const mod = document.createElement("div");
    mod.className = "note-module";
    mod.textContent = r.module;
    const snip = document.createElement("div");
    snip.className = "note-snippet";
    snip.textContent = r.snippet;
    li.append(name, mod, snip);
    li.onclick = () => openNote(r.path);
    ul.appendChild(li);
  });
}

async function refreshModules() {
  const d = await api("/api/modules");
  state.modules = d.modules;
  state.sortModes.modules = d.sortMode || "manual";
  $("module-sort").value = state.sortModes.modules;
  if (state.module && !state.modules.some((m) => m.name === state.module)) {
    state.module = null;
  }
  renderModules();
  if (!state.module) $("notes-title").textContent = "笔记";
}

async function selectModule(name) {
  if (isDirty() && !confirm("当前笔记有未保存修改，是否放弃？")) return;
  state.module = name;
  state.searching = false;
  $("search").value = "";
  $("notes-title").textContent = name;
  renderModules();
  clearEditor();
  await loadNotes();
}

async function loadNotes() {
  const d = await api("/api/notes?module=" + encodeURIComponent(state.module));
  state.sortModes.notes = d.sortMode || "manual";
  $("note-sort").value = state.sortModes.notes;
  $("note-sort").disabled = false;
  renderNotes(d.notes);
}

async function openNote(path) {
  if (isDirty() && !confirm("当前笔记有未保存修改，是否放弃？")) return;
  const d = await api("/api/note?path=" + encodeURIComponent(path));
  const parts = path.split("/");
  if (parts[0] !== state.module) {
    state.module = parts[0];
    state.searching = false;
    $("search").value = "";
    $("notes-title").textContent = state.module;
    renderModules();
  }
  state.note = { path };
  state.savedContent = d.content;
  $("note-title").value = nameFromPath(path);
  $("note-body").value = d.content;
  renderPreview();
  updateDirty();
  setActiveNote(path);
}

async function saveNote(opts) {
  const quiet = opts && opts.quiet;
  if (!state.module) { if (!quiet) toast("请先选择模块"); return; }
  const oldPath = state.note ? state.note.path : null;
  const content = $("note-body").value;
  const firstLine = (content.split("\n").find((l) => l.trim()) || "").trim().replace(/^#+\s*/, "");
  const title = $("note-title").value.trim() || firstLine || "未命名";
  const body = {
    module: state.module,
    title,
    content,
    path: state.note ? state.note.path : null,
  };
  const res = await api("/api/note", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  state.note = { path: res.path };
  state.savedContent = content;
  if (!quiet || document.activeElement !== $("note-title")) {
    $("note-title").value = nameFromPath(res.path);
  }
  updateDirty();
  if (!quiet) toast("已保存");
  // 自动保存时，只有新建或改名才刷新列表，避免打字时界面跳动
  if (!quiet || res.path !== oldPath) {
    if (!state.searching) {
      await loadNotes();
    }
    refreshModules();
  }
}

let autoSaveTimer = null;
function scheduleAutosave() {
  if (!state.module) return;
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => {
    saveNote({ quiet: true }).catch(() => {});
  }, 800);
}

async function deleteNote() {
  if (!state.note) { toast("当前没有打开的笔记"); return; }
  if (!confirm("确定删除这篇笔记？")) return;
  await api("/api/note?path=" + encodeURIComponent(state.note.path), { method: "DELETE" });
  state.note = null;
  clearEditor();
  toast("已删除");
  if (state.searching) {
    await doSearch();
  } else {
    await loadNotes();
  }
  refreshModules();
}

function newNote() {
  if (!state.module) { toast("请先选择或创建一个模块"); return; }
  if (isDirty() && !confirm("当前笔记有未保存修改，是否放弃？")) return;
  clearEditor();
  setViewMode("edit");
  $("note-title").focus();
  setActiveNote(null);
}

async function addModule() {
  const name = prompt("新模块名称：");
  if (!name || !name.trim()) return;
  await api("/api/modules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name.trim() }),
  });
  await refreshModules();
  selectModule(name.trim());
}

async function deleteModule(name) {
  const mod = (state.modules || []).find((m) => m.name === name);
  const msg = mod && mod.count > 0
    ? `确定删除模块“${name}”及其全部 ${mod.count} 篇笔记？此操作不可恢复。`
    : `确定删除模块“${name}”？`;
  if (!confirm(msg)) return;
  await api("/api/modules/" + encodeURIComponent(name), { method: "DELETE" });
  if (state.module === name) {
    state.module = null;
    state.note = null;
    clearEditor();
  }
  await refreshModules();
  toast("已删除");
}

async function uploadImage(file) {
  if (!file.type.startsWith("image/")) { toast("仅支持图片文件"); return; }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("module", state.module || "");
  const res = await api("/api/upload", { method: "POST", body: fd });
  insertText(`\n![${file.name.replace(/\.[^.]+$/, "")}](${res.md})\n`);
  toast("图片已插入");
}

function insertText(text) {
  const ta = $("note-body");
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
  ta.selectionStart = ta.selectionEnd = start + text.length;
  ta.focus();
  renderPreview();
  updateDirty();
}

async function doSearch() {
  const q = $("search").value.trim();
  if (!q) {
    state.searching = false;
    $("notes-title").textContent = state.module || "笔记";
    if (state.module) {
      const d = await api("/api/notes?module=" + encodeURIComponent(state.module));
      renderNotes(d.notes);
    }
    return;
  }
  state.searching = true;
  $("notes-title").textContent = "搜索结果";
  const d = await api("/api/search?q=" + encodeURIComponent(q));
  renderSearchResults(d.results);
}

function getDragAfterElement(container, y) {
  const items = [...container.querySelectorAll(".draggable:not(.dragging)")];
  return items.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return { offset, element: child };
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function dragSetup(container, type) {
  container.addEventListener("dragstart", (e) => {
    const li = e.target.closest(".draggable");
    if (!li) return;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", li.dataset.id);
    requestAnimationFrame(() => li.classList.add("dragging"));
  });
  container.addEventListener("dragend", () => {
    container.querySelectorAll(".dragging").forEach((el) => el.classList.remove("dragging"));
  });
  container.addEventListener("dragover", (e) => {
    e.preventDefault();
    const dragging = container.querySelector(".dragging");
    if (!dragging) return;
    const after = getDragAfterElement(container, e.clientY);
    if (after == null) container.appendChild(dragging);
    else container.insertBefore(dragging, after);
  });
  container.addEventListener("drop", async (e) => {
    e.preventDefault();
    container.querySelectorAll(".dragging").forEach((el) => el.classList.remove("dragging"));
    const items = [...container.querySelectorAll(".draggable")].map((li) => li.dataset.id);
    const payload = { type, items };
    if (type === "notes") payload.module = state.module;
    await api("/api/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (type === "modules") {
      await refreshModules();
    } else if (state.module && !state.searching) {
      await loadNotes();
    }
    toast("已调整排序");
  });
}

function showShutdown() {
  $("shutdown-overlay").classList.add("show");
}

function bindEvents() {
  $("btn-add-module").onclick = addModule;
  $("btn-new-note").onclick = newNote;
  $("btn-save").onclick = saveNote;
  $("btn-delete").onclick = deleteNote;
  $("btn-edit-mode").onclick = () => setViewMode("edit");
  $("btn-preview-mode").onclick = () => setViewMode("preview");
  $("btn-toggle-sidebar").onclick = toggleSidebar;
  $("btn-upload").onclick = () => {
    $("file-input").value = "";
    $("file-input").click();
  };
  $("file-input").onchange = () => {
    [...$("file-input").files].forEach(uploadImage);
  };

  $("btn-shutdown").onclick = async () => {
    // 桌面窗口：一次点击直接退出（退出前由本地壳静默保存未写内容）
    if (window.pywebview && window.pywebview.api && window.pywebview.api.quit_app) {
      try { await window.pywebview.api.quit_app(); return; } catch (e) {}
    }
    // 浏览器兜底：停掉本地服务并提示
    try { await fetch("/api/shutdown", { method: "POST" }); } catch (e) {}
    showShutdown();
  };

  $("module-sort").onchange = async () => {
    await api("/api/sortmode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "modules", mode: $("module-sort").value }),
    });
    await refreshModules();
  };
  $("note-sort").onchange = async () => {
    await api("/api/sortmode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "notes", mode: $("note-sort").value }),
    });
    if (state.module) await loadNotes();
  };

  dragSetup($("module-list"), "modules");
  dragSetup($("note-list"), "notes");

  const body = $("note-body");
  body.addEventListener("input", () => {
    renderPreview();
    updateDirty();
    scheduleAutosave();
  });

  $("note-title").addEventListener("input", () => {
    scheduleAutosave();
  });

  body.addEventListener("paste", (e) => {
    const items = [...(e.clipboardData && e.clipboardData.items || [])]
      .filter((i) => i.type.startsWith("image/"));
    if (items.length) {
      e.preventDefault();
      items.forEach((i) => uploadImage(i.getAsFile()));
    }
  });

  body.addEventListener("dragover", (e) => e.preventDefault());
  body.addEventListener("drop", (e) => {
    const files = [...(e.dataTransfer && e.dataTransfer.files || [])]
      .filter((f) => f.type.startsWith("image/"));
    if (files.length) {
      e.preventDefault();
      files.forEach(uploadImage);
    }
  });

  let searchTimer = null;
  $("search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(doSearch, 300);
  });

  document.addEventListener("keydown", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    const key = e.key.toLowerCase();
    if (key === "s") { e.preventDefault(); saveNote(); }
    if (key === "n") { e.preventDefault(); newNote(); }
    if (key === "k") { e.preventDefault(); $("search").focus(); $("search").select(); }
    if (key === "b") { e.preventDefault(); toggleSidebar(); }
    if (key === "e") {
      e.preventDefault();
      setViewMode(state.viewMode === "edit" ? "preview" : "edit");
    }
  });
}

// 桌面壳关闭窗口前调用：返回未保存内容（已保存则返回 null），由本地进程直接写盘
window.__znoteSnapshot = function () {
  if (!state.module) return null;
  const content = $("note-body").value;
  const title = $("note-title").value.trim();
  if (!state.note && !content.trim() && !title) return null;
  if (state.note && content === state.savedContent) return null;
  const firstLine = (content.split("\n").find((l) => l.trim()) || "").trim().replace(/^#+\s*/, "");
  return {
    module: state.module,
    title: title || firstLine || "未命名",
    content,
    path: state.note ? state.note.path : "",
  };
};

async function init() {
  bindEvents();
  setViewMode(state.viewMode);
  await refreshModules();
}

init().catch((err) => {
  alert("初始化失败: " + err.message);
});
