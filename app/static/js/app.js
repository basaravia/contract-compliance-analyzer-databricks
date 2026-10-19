"use strict";
/**
 * Frontend SPA del Analizador de Cumplimiento Contractual.
 *
 * Reglas de seguridad seguidas en este archivo:
 * - Ningún dato proveniente del backend se inserta con innerHTML: siempre
 *   textContent / creación de nodos, para evitar XSS almacenado (un contrato
 *   o una regla podría contener texto con marcado HTML).
 * - Toda escritura (POST/PUT/PATCH/DELETE) pasa por `apiFetch`, que añade el
 *   header X-CSRF-Token leído de la cookie `ccap_csrf` (double-submit cookie).
 */

const DPI = 150;
const PX_PER_PT = DPI / 72;
const STATUS_LABELS = {
  cumple: "Cumple",
  no_cumple: "No cumple",
  parcial: "Parcial",
  no_determinable: "No determinable",
  requiere_revision: "Requiere revisión",
};
const HANDLE_SIZE = 9; // px de canvas

const state = {
  documents: [],
  allRules: [],
  analyses: [],
  currentAnalysis: null, // AnalysisDetailOut de la pestaña Análisis
  ruleEditor: { original: null, draft: null, activeTab: "form" },
  review: {
    analysis: null,
    document: null,
    currentPage: 1,
    image: null,
    mode: "select", // 'select' | 'create'
    selectedFindingId: null,
    drag: null, // {type:'move'|'resize'|'create', ...}
    pendingCreateRectPx: null,
  },
};

let authMode = "local";

// ---------------------------------------------------------------------------
// Helpers de red / CSRF
// ---------------------------------------------------------------------------
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  opts.headers = new Headers(options.headers || {});
  opts.credentials = "same-origin";
  const method = (opts.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = getCookie("ccap_csrf");
    if (token) opts.headers.set("X-CSRF-Token", token);
  }
  const resp = await fetch(url, opts);
  if (resp.status === 401 && authMode !== "local") {
    window.location.href = "/login";  // sesión caducada o revocada
  }
  return resp;
}

async function apiJson(url, method, body) {
  return apiFetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function extractErrorMessage(resp) {
  try {
    const data = await resp.json();
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail === "object") {
      let msg = data.detail.message || JSON.stringify(data.detail);
      if (Array.isArray(data.detail.errors) && data.detail.errors.length) {
        msg += ` (${data.detail.errors.length} error(es) de formato)`;
      }
      return msg;
    }
    return `Error HTTP ${resp.status}`;
  } catch {
    return `Error HTTP ${resp.status}`;
  }
}

async function downloadBlob(url, filename) {
  const resp = await apiFetch(url);
  if (!resp.ok) {
    alert("No se pudo descargar el archivo: " + (await extractErrorMessage(resp)));
    return;
  }
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

function setMsg(el, text, kind) {
  el.textContent = text || "";
  el.className = "form-msg" + (kind ? " " + kind : "");
}

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Navegación por pestañas
// ---------------------------------------------------------------------------
function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
}

// ---------------------------------------------------------------------------
// Documentos
// ---------------------------------------------------------------------------
async function loadDocuments() {
  const filter = document.getElementById("doc-filter-type").value;
  const url = "/api/documents" + (filter ? `?doc_type=${encodeURIComponent(filter)}` : "");
  const resp = await apiFetch(url);
  if (!resp.ok) return;
  const docs = await resp.json();
  state.documents = docs;
  renderDocumentsTable(docs);
  populateAnalysisDocSelect(docs.filter((d) => d.doc_type === "contrato"));
}

function renderDocumentsTable(docs) {
  const tbody = document.getElementById("documents-tbody");
  const tpl = document.getElementById("template-doc-row");
  tbody.textContent = "";
  for (const doc of docs) {
    const row = tpl.content.cloneNode(true);
    row.querySelector(".cell-title").textContent = doc.title || doc.original_filename;
    row.querySelector(".cell-type").textContent = doc.doc_type;
    row.querySelector(".cell-jurisdiction").textContent = doc.jurisdiction;
    row.querySelector(".cell-pages").textContent = String(doc.page_count);
    row.querySelector(".cell-status").textContent = doc.extraction_status;
    row.querySelector(".cell-scanned").textContent = doc.is_scanned ? "Sí" : "No";
    row.querySelector(".btn-delete-doc").addEventListener("click", () => deleteDocument(doc.id));
    tbody.appendChild(row);
  }
}

async function deleteDocument(id) {
  if (!confirm("¿Eliminar este documento? Esta acción no se puede deshacer.")) return;
  const resp = await apiFetch(`/api/documents/${id}`, { method: "DELETE" });
  if (resp.status === 204) {
    await loadDocuments();
  } else {
    alert("No se pudo eliminar: " + (await extractErrorMessage(resp)));
  }
}

function initUploadForm() {
  const form = document.getElementById("upload-form");
  const msg = document.getElementById("upload-msg");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setMsg(msg, "Subiendo...", "");
    const fd = new FormData();
    fd.append("doc_type", document.getElementById("upload-doc-type").value);
    fd.append("title", document.getElementById("upload-title").value);
    fd.append("jurisdiction", document.getElementById("upload-jurisdiction").value);
    fd.append("file", document.getElementById("upload-file").files[0]);
    const resp = await apiFetch("/api/documents", { method: "POST", body: fd });
    if (resp.ok) {
      setMsg(msg, "Documento subido correctamente.", "success");
      form.reset();
      document.getElementById("upload-jurisdiction").value =
        document.getElementById("upload-jurisdiction").defaultValue;
      await loadDocuments();
    } else {
      setMsg(msg, await extractErrorMessage(resp), "error");
    }
  });
  document.getElementById("refresh-docs").addEventListener("click", loadDocuments);
  document.getElementById("doc-filter-type").addEventListener("change", loadDocuments);
}

// ---------------------------------------------------------------------------
// Reglas
// ---------------------------------------------------------------------------
function addReferenceRow(container, citation = "", page = "") {
  const tpl = document.getElementById("template-reference-row");
  const node = tpl.content.cloneNode(true);
  const wrap = node.querySelector(".reference-row");
  wrap.querySelector(".ref-citation").value = citation;
  wrap.querySelector(".ref-page").value = page;
  wrap.querySelector(".btn-remove-reference").addEventListener("click", () => wrap.remove());
  container.appendChild(node);
}

function collectReferences(container) {
  const refs = [];
  container.querySelectorAll(".reference-row").forEach((row) => {
    const citation = row.querySelector(".ref-citation").value.trim();
    if (!citation) return;
    const pageVal = row.querySelector(".ref-page").value;
    refs.push({ citation, page: pageVal ? parseInt(pageVal, 10) : null });
  });
  return refs;
}

async function loadRules() {
  const resp = await apiFetch("/api/rules");
  if (!resp.ok) return;
  state.allRules = await resp.json();
  renderRulesTable();
  populateAnalysisRulesList();
}

function renderRulesTable() {
  const onlyActive = document.getElementById("rules-active-only").checked;
  const tbody = document.getElementById("rules-tbody");
  const tpl = document.getElementById("template-rule-row");
  tbody.textContent = "";
  const rules = onlyActive ? state.allRules.filter((r) => r.active) : state.allRules;
  for (const rule of rules) {
    const row = tpl.content.cloneNode(true);
    row.querySelector(".cell-name").textContent = rule.name;
    row.querySelector(".cell-category").textContent = rule.category || "—";
    row.querySelector(".cell-severity").textContent = rule.severity;
    row.querySelector(".cell-jurisdiction").textContent = rule.jurisdiction;
    const activeCell = row.querySelector(".cell-active");
    const activeSwitch = activeCell.querySelector(".switch");
    const activeLabel = activeCell.querySelector(".switch-label");
    activeSwitch.setAttribute("aria-checked", String(Boolean(rule.active)));
    activeSwitch.setAttribute("aria-label", rule.active ? "Desactivar regla" : "Activar regla");
    activeSwitch.title = rule.active ? "Esta regla se analizará" : "Esta regla se omitirá";
    activeSwitch.classList.toggle("on", Boolean(rule.active));
    activeLabel.textContent = rule.active ? "Activa: se analizará" : "Inactiva: se omitirá";
    const refsCell = row.querySelector(".cell-refs");
    if (rule.references.length === 0) {
      refsCell.textContent = "—";
    } else {
      const list = document.createElement("ul");
      list.style.margin = "0";
      list.style.paddingLeft = "1rem";
      for (const ref of rule.references) {
        const li = document.createElement("li");
        li.textContent = ref.citation + (ref.page ? ` (p. ${ref.page})` : "");
        list.appendChild(li);
      }
      refsCell.appendChild(list);
    }
    row.querySelector(".btn-toggle-rule").addEventListener("click", () => toggleRuleActive(rule));
    row.querySelector(".btn-edit-rule").addEventListener("click", () => openRuleEditor(rule));
    row.querySelector(".btn-delete-rule").addEventListener("click", () => deleteRule(rule.id));
    tbody.appendChild(row);
  }
}

async function toggleRuleActive(rule) {
  const resp = await apiJson(`/api/rules/${rule.id}`, "PUT", { active: !rule.active });
  if (resp.ok) {
    await loadRules();
  } else {
    alert("No se pudo actualizar la regla: " + (await extractErrorMessage(resp)));
  }
}

async function deleteRule(id) {
  if (!confirm("¿Eliminar esta regla?")) return;
  const resp = await apiFetch(`/api/rules/${id}`, { method: "DELETE" });
  if (resp.status === 204) {
    await loadRules();
  } else {
    alert("No se pudo eliminar: " + (await extractErrorMessage(resp)));
  }
}

function initRuleForm() {
  const form = document.getElementById("rule-form");
  const msg = document.getElementById("rule-msg");
  const refsContainer = document.getElementById("rule-references");
  document.getElementById("add-reference").addEventListener("click", () => addReferenceRow(refsContainer));
  addReferenceRow(refsContainer);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      name: document.getElementById("rule-name").value,
      description: document.getElementById("rule-description").value,
      jurisdiction: document.getElementById("rule-jurisdiction").value || "EC",
      category: document.getElementById("rule-category").value || null,
      severity: document.getElementById("rule-severity").value,
      active: true,
      references: collectReferences(refsContainer),
    };
    const resp = await apiJson("/api/rules", "POST", payload);
    if (resp.ok) {
      setMsg(msg, "Regla creada.", "success");
      form.reset();
      refsContainer.textContent = "";
      addReferenceRow(refsContainer);
      await loadRules();
    } else {
      setMsg(msg, await extractErrorMessage(resp), "error");
    }
  });

  document.getElementById("rules-active-only").addEventListener("change", renderRulesTable);
}

function editorPayloadFromForm() {
  const refs = [];
  document.querySelectorAll("#edit-rule-references .reference-row").forEach((row) => {
    const citation = row.querySelector(".ref-citation").value.trim();
    if (citation) refs.push({ citation, page: row.querySelector(".ref-page").value ? Number(row.querySelector(".ref-page").value) : null });
  });
  return {
    name: document.getElementById("edit-rule-name").value.trim(),
    description: document.getElementById("edit-rule-description").value.trim(),
    jurisdiction: document.getElementById("edit-rule-jurisdiction").value,
    category: document.getElementById("edit-rule-category").value.trim() || null,
    severity: document.getElementById("edit-rule-severity").value,
    active: document.getElementById("edit-rule-active-switch").getAttribute("aria-checked") === "true",
    references: refs,
  };
}

function editorSetForm(rule) {
  document.getElementById("edit-rule-name").value = rule.name || "";
  document.getElementById("edit-rule-description").value = rule.description || "";
  document.getElementById("edit-rule-jurisdiction").value = rule.jurisdiction || "EC";
  document.getElementById("edit-rule-category").value = rule.category || "";
  document.getElementById("edit-rule-severity").value = rule.severity || "media";
  const sw = document.getElementById("edit-rule-active-switch");
  sw.setAttribute("aria-checked", String(Boolean(rule.active)));
  sw.classList.toggle("on", Boolean(rule.active));
  document.getElementById("edit-rule-active-label").textContent = rule.active ? "Activa: se analizará" : "Inactiva: se omitirá";
  const refs = document.getElementById("edit-rule-references");
  refs.textContent = "";
  (rule.references || []).forEach((ref) => addReferenceRow(refs, ref.citation, ref.page));
  if (!refs.children.length) addReferenceRow(refs);
}

function editorSetJson(rule) {
  document.getElementById("rule-editor-json").value = JSON.stringify(editorPayloadFromRule(rule), null, 2);
}

function editorPayloadFromRule(rule) {
  return { name: rule.name, description: rule.description, jurisdiction: rule.jurisdiction, category: rule.category || null, severity: rule.severity, active: Boolean(rule.active), references: rule.references || [] };
}

function switchRuleEditorTab(tab) {
  state.ruleEditor.activeTab = tab;
  document.querySelectorAll("[data-editor-tab]").forEach((b) => { const active = b.dataset.editorTab === tab; b.classList.toggle("active", active); b.setAttribute("aria-selected", String(active)); });
  document.getElementById("rule-editor-panel-form").hidden = tab !== "form";
  document.getElementById("rule-editor-panel-json").hidden = tab !== "json";
  document.getElementById("rule-editor-panel-form").classList.toggle("active", tab === "form");
  document.getElementById("rule-editor-panel-json").classList.toggle("active", tab === "json");
  if (tab === "json") document.getElementById("rule-editor-json").value = JSON.stringify(editorPayloadFromForm(), null, 2);
}

function openRuleEditor(rule) {
  state.ruleEditor.original = rule;
  state.ruleEditor.draft = editorPayloadFromRule(rule);
  editorSetForm(state.ruleEditor.draft);
  editorSetJson(state.ruleEditor.draft);
  setMsg(document.getElementById("rule-editor-msg"), "", "");
  setMsg(document.getElementById("rule-editor-json-error"), "", "");
  document.getElementById("rule-editor-overlay").hidden = false;
  switchRuleEditorTab("form");
}

function closeRuleEditor() { document.getElementById("rule-editor-overlay").hidden = true; state.ruleEditor.original = null; state.ruleEditor.draft = null; }

function validateRuleEditorJson() {
  try {
    const parsed = JSON.parse(document.getElementById("rule-editor-json").value);
    if (!parsed.name || !parsed.description || !Array.isArray(parsed.references) || !["alta", "media", "baja"].includes(parsed.severity)) throw new Error("name, description, severity y references son obligatorios");
    if (typeof parsed.active !== "boolean") throw new Error("active debe ser booleano");
    return parsed;
  } catch (err) { setMsg(document.getElementById("rule-editor-json-error"), `JSON inválido: ${err.message}`, "error"); return null; }
}

function initRuleEditor() {
  document.querySelectorAll("[data-editor-tab]").forEach((b) => b.addEventListener("click", () => switchRuleEditorTab(b.dataset.editorTab)));
  document.getElementById("rule-editor-active-switch");
  document.getElementById("edit-rule-active-switch").addEventListener("click", () => {
    const sw = document.getElementById("edit-rule-active-switch"); const active = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", String(active)); sw.classList.toggle("on", active); document.getElementById("edit-rule-active-label").textContent = active ? "Activa: se analizará" : "Inactiva: se omitirá";
  });
  document.querySelectorAll("#rule-editor-form input, #rule-editor-form textarea, #rule-editor-form select").forEach((el) => el.addEventListener("input", () => { document.getElementById("rule-editor-json").value = JSON.stringify(editorPayloadFromForm(), null, 2); }));
  document.getElementById("edit-add-reference").addEventListener("click", () => { addReferenceRow(document.getElementById("edit-rule-references")); document.getElementById("rule-editor-json").value = JSON.stringify(editorPayloadFromForm(), null, 2); });
  document.getElementById("rule-editor-json").addEventListener("input", () => { const parsed = validateRuleEditorJson(); if (parsed) { state.ruleEditor.draft = parsed; editorSetForm(parsed); setMsg(document.getElementById("rule-editor-json-error"), "JSON válido", "success"); } });
  document.getElementById("rule-editor-save").addEventListener("click", async () => { const payload = state.ruleEditor.activeTab === "json" ? validateRuleEditorJson() : editorPayloadFromForm(); if (!payload) return; const resp = await apiJson(`/api/rules/${state.ruleEditor.original.id}`, "PUT", payload); if (!resp.ok) { setMsg(document.getElementById("rule-editor-msg"), await extractErrorMessage(resp), "error"); return; } closeRuleEditor(); await loadRules(); });
  document.getElementById("rule-editor-close").addEventListener("click", closeRuleEditor); document.getElementById("rule-editor-cancel").addEventListener("click", closeRuleEditor);
}

function initImportForms() {
  const textForm = document.getElementById("import-text-form");
  const textMsg = document.getElementById("import-text-msg");
  const errorList = document.getElementById("import-text-errors");
  textForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorList.textContent = "";
    const text = document.getElementById("import-text-area").value;
    const resp = await apiJson("/api/rules/import-text", "POST", { text });
    if (resp.ok) {
      setMsg(textMsg, "Reglas importadas correctamente.", "success");
      document.getElementById("import-text-area").value = "";
      await loadRules();
    } else {
      let data;
      try {
        data = await resp.json();
      } catch {
        data = null;
      }
      if (data && data.detail && Array.isArray(data.detail.errors)) {
        setMsg(textMsg, data.detail.message || "Errores de formato", "error");
        for (const err of data.detail.errors) {
          const li = document.createElement("li");
          li.textContent = `Bloque ${err.bloque}: ${err.error}`;
          errorList.appendChild(li);
        }
      } else {
        setMsg(textMsg, data && data.detail ? String(data.detail) : `Error HTTP ${resp.status}`, "error");
      }
    }
  });

  const jsonForm = document.getElementById("import-json-form");
  const jsonMsg = document.getElementById("import-json-msg");
  jsonForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("import-json-file");
    const file = fileInput.files[0];
    if (!file) {
      setMsg(jsonMsg, "Selecciona un archivo JSON.", "error");
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      setMsg(jsonMsg, "El archivo no contiene JSON válido.", "error");
      return;
    }
    const payload = Array.isArray(parsed) ? { rules: parsed } : parsed;
    const resp = await apiJson("/api/rules/import", "POST", payload);
    if (resp.ok) {
      setMsg(jsonMsg, "Reglas importadas correctamente.", "success");
      fileInput.value = "";
      await loadRules();
    } else {
      setMsg(jsonMsg, await extractErrorMessage(resp), "error");
    }
  });
}

// ---------------------------------------------------------------------------
// Análisis
// ---------------------------------------------------------------------------
function populateAnalysisDocSelect(contractDocs) {
  const select = document.getElementById("analysis-doc-select");
  const previous = select.value;
  select.textContent = "";
  for (const doc of contractDocs) {
    const opt = document.createElement("option");
    opt.value = doc.id;
    opt.textContent = `${doc.title || doc.original_filename} (${doc.page_count} pág.)`;
    select.appendChild(opt);
  }
  if (previous) select.value = previous;
}

function populateAnalysisRulesList() {
  const container = document.getElementById("analysis-rules-list");
  container.textContent = "";
  const activeRules = state.allRules.filter((r) => r.active);
  for (const rule of activeRules) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = rule.id;
    checkbox.className = "analysis-rule-checkbox";
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` ${rule.name} (${rule.severity})`));
    container.appendChild(label);
  }
}

function ruleName(ruleId) {
  const rule = state.allRules.find((r) => r.id === ruleId);
  return rule ? rule.name : ruleId;
}

function initAnalysisForm() {
  const form = document.getElementById("analysis-form");
  const msg = document.getElementById("analysis-msg");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const docId = document.getElementById("analysis-doc-select").value;
    if (!docId) {
      setMsg(msg, "Selecciona un contrato.", "error");
      return;
    }
    const ruleIds = Array.from(document.querySelectorAll(".analysis-rule-checkbox:checked")).map((c) => c.value);
    setMsg(msg, "Ejecutando análisis...", "");
    const resp = await apiJson("/api/analyses", "POST", { contract_document_id: docId, rule_ids: ruleIds });
    if (resp.ok) {
      const analysis = await resp.json();
      setMsg(msg, `Análisis completado: ${analysis.findings.length} hallazgo(s).`, "success");
      state.currentAnalysis = analysis;
      renderAnalysisFindings(analysis);
      await loadAnalysesList();
    } else {
      setMsg(msg, await extractErrorMessage(resp), "error");
    }
  });

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      await apiFetch("/auth/logout", { method: "POST", redirect: "manual" });
      window.location.href = "/login";
    });
  }
  document.getElementById("refresh-analyses").addEventListener("click", loadAnalysesList);
  document.getElementById("export-pdf-btn").addEventListener("click", () => {
    if (state.currentAnalysis) {
      downloadBlob(`/api/analyses/${state.currentAnalysis.id}/export.pdf`, `analisis-${state.currentAnalysis.id}.pdf`);
    }
  });
  document.getElementById("export-workpaper-btn").addEventListener("click", () => {
    if (state.currentAnalysis) {
      downloadBlob(`/api/analyses/${state.currentAnalysis.id}/papel-trabajo.xlsx`, `papel-trabajo-${state.currentAnalysis.id}.xlsx`);
    }
  });
  document.getElementById("export-json-btn").addEventListener("click", () => {
    if (state.currentAnalysis) {
      downloadBlob(`/api/analyses/${state.currentAnalysis.id}/export.json`, `analisis-${state.currentAnalysis.id}.json`);
    }
  });
  document.getElementById("open-review-btn").addEventListener("click", () => {
    if (state.currentAnalysis) openReview(state.currentAnalysis.id);
  });
}

async function loadAnalysesList() {
  const resp = await apiFetch("/api/analyses");
  if (!resp.ok) return;
  state.analyses = await resp.json();
  renderAnalysesTable();
}

function renderAnalysesTable() {
  const tbody = document.getElementById("analyses-tbody");
  const tpl = document.getElementById("template-analysis-row");
  tbody.textContent = "";
  for (const a of state.analyses) {
    const row = tpl.content.cloneNode(true);
    row.querySelector(".cell-id").textContent = a.id.slice(0, 8);
    const doc = state.documents.find((d) => d.id === a.contract_document_id);
    row.querySelector(".cell-doc").textContent = doc ? doc.title || doc.original_filename : a.contract_document_id.slice(0, 8);
    row.querySelector(".cell-status").textContent = a.status;
    row.querySelector(".cell-created").textContent = fmtDate(a.created_at);
    row.querySelector(".btn-view-analysis").addEventListener("click", () => viewAnalysis(a.id));
    tbody.appendChild(row);
  }
}

async function viewAnalysis(id) {
  const resp = await apiFetch(`/api/analyses/${id}`);
  if (!resp.ok) {
    alert("No se pudo cargar el análisis: " + (await extractErrorMessage(resp)));
    return;
  }
  const analysis = await resp.json();
  state.currentAnalysis = analysis;
  renderAnalysisFindings(analysis);
}

function renderAnalysisFindings(analysis) {
  const card = document.getElementById("analysis-findings-card");
  card.hidden = false;
  const tbody = document.getElementById("findings-tbody");
  const tpl = document.getElementById("template-finding-row");
  tbody.textContent = "";
  for (const f of analysis.findings) {
    const row = tpl.content.cloneNode(true);
    row.querySelector(".cell-rule").textContent = ruleName(f.rule_id);
    row.querySelector(".cell-status").appendChild(statusPill(f.status));
    row.querySelector(".cell-severity").textContent = f.severity;
    row.querySelector(".cell-confidence").textContent = f.confidence.toFixed(2);
    row.querySelector(".cell-manual").textContent = f.is_manual ? "Sí" : "No";
    row.querySelector(".cell-edited").textContent = f.edited ? "Sí" : "No";
    row.querySelector(".cell-page").textContent = f.page != null ? String(f.page) : "—";
    tbody.appendChild(row);
  }
}

function statusPill(status) {
  const span = document.createElement("span");
  span.className = "status-pill status-" + status;
  span.textContent = STATUS_LABELS[status] || status;
  return span;
}

// ---------------------------------------------------------------------------
// Revisión visual (bboxes sobre el PDF)
// ---------------------------------------------------------------------------
async function openReview(analysisId) {
  const [analysisResp] = await Promise.all([apiFetch(`/api/analyses/${analysisId}`)]);
  if (!analysisResp.ok) {
    alert("No se pudo cargar el análisis: " + (await extractErrorMessage(analysisResp)));
    return;
  }
  const analysis = await analysisResp.json();
  const docResp = await apiFetch(`/api/documents/${analysis.contract_document_id}`);
  if (!docResp.ok) {
    alert("No se pudo cargar el documento del contrato: " + (await extractErrorMessage(docResp)));
    return;
  }
  const doc = await docResp.json();

  state.review.analysis = analysis;
  state.review.document = doc;
  state.review.currentPage = 1;
  state.review.selectedFindingId = null;
  state.review.mode = "select";
  state.review.pendingCreateRectPx = null;

  document.getElementById("review-empty-hint").hidden = true;
  document.getElementById("review-container").hidden = false;
  document.getElementById("toggle-create-mode-btn").textContent = "Modo: seleccionar";
  populateCreateFindingRuleSelect(analysis);
  switchTab("revision");
  await loadReviewPage();
}

function populateCreateFindingRuleSelect(analysis) {
  const select = document.getElementById("create-finding-rule-select");
  select.textContent = "";
  const ruleIds = analysis.rule_ids && analysis.rule_ids.length ? analysis.rule_ids : state.allRules.map((r) => r.id);
  for (const ruleId of ruleIds) {
    const opt = document.createElement("option");
    opt.value = ruleId;
    opt.textContent = ruleName(ruleId);
    select.appendChild(opt);
  }
}

function reviewFindingsOnCurrentPage() {
  const rv = state.review;
  if (!rv.analysis) return [];
  return rv.analysis.findings.filter(
    (f) =>
      f.page === rv.currentPage &&
      f.bbox_x0 != null &&
      f.bbox_y0 != null &&
      f.bbox_x1 != null &&
      f.bbox_y1 != null
  );
}

async function loadReviewPage() {
  const rv = state.review;
  const canvas = document.getElementById("review-canvas");
  document.getElementById("page-indicator").textContent = `Página ${rv.currentPage} / ${rv.document.page_count}`;
  document.getElementById("prev-page-btn").disabled = rv.currentPage <= 1;
  document.getElementById("next-page-btn").disabled = rv.currentPage >= rv.document.page_count;

  const img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    rv.image = img;
    redrawCanvas();
  };
  img.src = `/api/documents/${rv.document.id}/pages/${rv.currentPage}.png?dpi=${DPI}`;
  selectFinding(null);
}

function redrawCanvas() {
  const rv = state.review;
  const canvas = document.getElementById("review-canvas");
  const ctx = canvas.getContext("2d");
  if (!rv.image) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(rv.image, 0, 0);

  for (const f of reviewFindingsOnCurrentPage()) {
    const rectPx = bboxToPx(f);
    const isSelected = f.id === rv.selectedFindingId;
    drawRect(ctx, rectPx, statusColor(f.status), isSelected);
    if (isSelected) drawHandles(ctx, rectPx);
  }

  if (rv.drag && rv.drag.type === "create" && rv.drag.current) {
    const rectPx = normalizeRect(rv.drag.start, rv.drag.current);
    drawRect(ctx, rectPx, "#1d4ed8", false, true);
  } else if (rv.pendingCreateRectPx) {
    drawRect(ctx, rv.pendingCreateRectPx, "#1d4ed8", true, true);
  }
}

function statusColor(status) {
  const colors = {
    cumple: "#218c21",
    no_cumple: "#cc1a1a",
    parcial: "#d98c00",
    no_determinable: "#737373",
    requiere_revision: "#0059cc",
  };
  return colors[status] || "#737373";
}

function drawRect(ctx, rect, color, selected, dashed) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = selected ? 3 : 2;
  if (dashed) ctx.setLineDash([6, 4]);
  ctx.strokeRect(rect.x0, rect.y0, rect.x1 - rect.x0, rect.y1 - rect.y0);
  ctx.globalAlpha = 0.12;
  ctx.fillStyle = color;
  ctx.fillRect(rect.x0, rect.y0, rect.x1 - rect.x0, rect.y1 - rect.y0);
  ctx.restore();
}

function drawHandles(ctx, rect) {
  const points = handlePoints(rect);
  ctx.save();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#1d4ed8";
  ctx.lineWidth = 1.5;
  for (const key in points) {
    const p = points[key];
    ctx.beginPath();
    ctx.rect(p.x - HANDLE_SIZE / 2, p.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

function handlePoints(rect) {
  const midX = (rect.x0 + rect.x1) / 2;
  const midY = (rect.y0 + rect.y1) / 2;
  return {
    nw: { x: rect.x0, y: rect.y0 },
    n: { x: midX, y: rect.y0 },
    ne: { x: rect.x1, y: rect.y0 },
    e: { x: rect.x1, y: midY },
    se: { x: rect.x1, y: rect.y1 },
    s: { x: midX, y: rect.y1 },
    sw: { x: rect.x0, y: rect.y1 },
    w: { x: rect.x0, y: midY },
  };
}

function bboxToPx(f) {
  return { x0: f.bbox_x0 * PX_PER_PT, y0: f.bbox_y0 * PX_PER_PT, x1: f.bbox_x1 * PX_PER_PT, y1: f.bbox_y1 * PX_PER_PT };
}

function pxRectToBboxPt(rect, canvas) {
  let x0 = Math.max(0, Math.min(rect.x0, canvas.width));
  let x1 = Math.max(0, Math.min(rect.x1, canvas.width));
  let y0 = Math.max(0, Math.min(rect.y0, canvas.height));
  let y1 = Math.max(0, Math.min(rect.y1, canvas.height));
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  return { x0: x0 / PX_PER_PT, y0: y0 / PX_PER_PT, x1: x1 / PX_PER_PT, y1: y1 / PX_PER_PT };
}

function normalizeRect(a, b) {
  return {
    x0: Math.min(a.x, b.x),
    y0: Math.min(a.y, b.y),
    x1: Math.max(a.x, b.x),
    y1: Math.max(a.y, b.y),
  };
}

function pointInRect(pos, rect, tolerance = 0) {
  return (
    pos.x >= rect.x0 - tolerance &&
    pos.x <= rect.x1 + tolerance &&
    pos.y >= rect.y0 - tolerance &&
    pos.y <= rect.y1 + tolerance
  );
}

function getHandleAt(pos, rect) {
  const points = handlePoints(rect);
  for (const key in points) {
    const p = points[key];
    if (Math.abs(pos.x - p.x) <= HANDLE_SIZE && Math.abs(pos.y - p.y) <= HANDLE_SIZE) {
      return key;
    }
  }
  return null;
}

function resizeRectByHandle(orig, handle, pos) {
  const rect = { ...orig };
  if (handle.includes("n")) rect.y0 = pos.y;
  if (handle.includes("s")) rect.y1 = pos.y;
  if (handle.includes("w")) rect.x0 = pos.x;
  if (handle.includes("e")) rect.x1 = pos.x;
  return rect;
}

function canvasPos(evt, canvas) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return { x: (evt.clientX - rect.left) * scaleX, y: (evt.clientY - rect.top) * scaleY };
}

function findFindingById(id) {
  const rv = state.review;
  if (!rv.analysis) return null;
  return rv.analysis.findings.find((f) => f.id === id) || null;
}

function getFindingAtPos(pos) {
  const candidates = reviewFindingsOnCurrentPage()
    .map((f) => ({ f, rect: bboxToPx(f) }))
    .filter(({ rect }) => pointInRect(pos, rect, 2));
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => {
    const areaA = (a.rect.x1 - a.rect.x0) * (a.rect.y1 - a.rect.y0);
    const areaB = (b.rect.x1 - b.rect.x0) * (b.rect.y1 - b.rect.y0);
    return areaA - areaB;
  });
  return candidates[0].f;
}

function initCanvasInteraction() {
  const canvas = document.getElementById("review-canvas");

  canvas.addEventListener("mousedown", (e) => {
    const rv = state.review;
    if (!rv.image) return;
    const pos = canvasPos(e, canvas);

    if (rv.mode === "create") {
      rv.drag = { type: "create", start: pos, current: pos };
      return;
    }

    if (rv.selectedFindingId) {
      const f = findFindingById(rv.selectedFindingId);
      if (f && f.page === rv.currentPage) {
        const rectPx = bboxToPx(f);
        const handle = getHandleAt(pos, rectPx);
        if (handle) {
          rv.drag = { type: "resize", handle, findingId: f.id, orig: rectPx, preview: rectPx };
          return;
        }
        if (pointInRect(pos, rectPx)) {
          rv.drag = { type: "move", findingId: f.id, orig: rectPx, start: pos, preview: rectPx };
          return;
        }
      }
    }

    const hit = getFindingAtPos(pos);
    if (hit) {
      selectFinding(hit.id);
      const rectPx = bboxToPx(hit);
      rv.drag = { type: "move", findingId: hit.id, orig: rectPx, start: pos, preview: rectPx };
    } else {
      selectFinding(null);
    }
  });

  canvas.addEventListener("mousemove", (e) => {
    const rv = state.review;
    if (!rv.drag) return;
    const pos = canvasPos(e, canvas);
    if (rv.drag.type === "create") {
      rv.drag.current = pos;
    } else if (rv.drag.type === "move") {
      const dx = pos.x - rv.drag.start.x;
      const dy = pos.y - rv.drag.start.y;
      const o = rv.drag.orig;
      rv.drag.preview = { x0: o.x0 + dx, y0: o.y0 + dy, x1: o.x1 + dx, y1: o.y1 + dy };
    } else if (rv.drag.type === "resize") {
      rv.drag.preview = resizeRectByHandle(rv.drag.orig, rv.drag.handle, pos);
    }
    redrawCanvas();
  });

  window.addEventListener("mouseup", async (e) => {
    const rv = state.review;
    if (!rv.drag) return;
    const drag = rv.drag;
    rv.drag = null;

    if (drag.type === "create") {
      const rectPx = normalizeRect(drag.start, drag.current || drag.start);
      if (Math.abs(rectPx.x1 - rectPx.x0) < 6 || Math.abs(rectPx.y1 - rectPx.y0) < 6) {
        redrawCanvas();
        return;
      }
      rv.pendingCreateRectPx = rectPx;
      showCreateForm();
      redrawCanvas();
      return;
    }

    if (drag.type === "move" || drag.type === "resize") {
      const canvas = document.getElementById("review-canvas");
      const bboxPt = pxRectToBboxPt(drag.preview, canvas);
      await patchFindingBbox(drag.findingId, bboxPt);
    }
  });

  canvas.addEventListener("keydown", (e) => {
    if ((e.key === "Delete" || e.key === "Backspace") && state.review.selectedFindingId) {
      e.preventDefault();
      deleteSelectedFinding();
    }
  });
}

async function patchFindingBbox(findingId, bboxPt) {
  const resp = await apiJson(`/api/findings/${findingId}`, "PATCH", { bbox: bboxPt, recalculate: true });
  if (!resp.ok) {
    alert("No se pudo actualizar el hallazgo: " + (await extractErrorMessage(resp)));
    redrawCanvas();
    return;
  }
  const updated = await resp.json();
  replaceFindingInState(updated);
  redrawCanvas();
  if (state.review.selectedFindingId === updated.id) renderFindingDetail(updated);
}

function replaceFindingInState(updated) {
  const rv = state.review;
  const idx = rv.analysis.findings.findIndex((f) => f.id === updated.id);
  if (idx >= 0) rv.analysis.findings[idx] = updated;
  else rv.analysis.findings.push(updated);
  if (state.currentAnalysis && state.currentAnalysis.id === rv.analysis.id) {
    const idx2 = state.currentAnalysis.findings.findIndex((f) => f.id === updated.id);
    if (idx2 >= 0) state.currentAnalysis.findings[idx2] = updated;
    else state.currentAnalysis.findings.push(updated);
    renderAnalysisFindings(state.currentAnalysis);
  }
}

function selectFinding(id) {
  state.review.selectedFindingId = id;
  document.getElementById("create-finding-form").hidden = true;
  state.review.pendingCreateRectPx = null;
  const detailEmpty = document.getElementById("finding-detail-empty");
  const detailContent = document.getElementById("finding-detail-content");
  if (!id) {
    detailEmpty.hidden = false;
    detailContent.hidden = true;
    redrawCanvas();
    return;
  }
  const f = findFindingById(id);
  if (!f) return;
  detailEmpty.hidden = true;
  detailContent.hidden = false;
  renderFindingDetail(f);
  redrawCanvas();
}

function renderFindingDetail(f) {
  const dl = document.getElementById("finding-detail-dl");
  dl.textContent = "";
  const entries = [
    ["Regla", ruleName(f.rule_id)],
    ["Estado", STATUS_LABELS[f.status] || f.status],
    ["Severidad", f.severity],
    ["Confianza", f.confidence.toFixed(2)],
    ["Manual", f.is_manual ? "Sí" : "No"],
    ["Editado", f.edited ? "Sí" : "No"],
    ["Página", f.page != null ? String(f.page) : "—"],
    ["Justificación", f.justification || "—"],
    ["Texto de evidencia", f.evidence_text || "(sin evidencia extraída)"],
  ];
  for (const [label, value] of entries) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  if (f.normative_refs && f.normative_refs.length) {
    const dt = document.createElement("dt");
    dt.textContent = "Referencias normativas";
    dl.appendChild(dt);
    const dd = document.createElement("dd");
    const list = document.createElement("ul");
    list.style.margin = "0";
    list.style.paddingLeft = "1rem";
    for (const ref of f.normative_refs) {
      const li = document.createElement("li");
      li.textContent = (ref.citation || "") + (ref.page ? ` (p. ${ref.page})` : "");
      list.appendChild(li);
    }
    dd.appendChild(list);
    dl.appendChild(dd);
  }
  document.getElementById("finding-status-select").value = f.status;
}

function showCreateForm() {
  document.getElementById("finding-detail-empty").hidden = true;
  document.getElementById("finding-detail-content").hidden = true;
  document.getElementById("create-finding-form").hidden = false;
}

async function deleteSelectedFinding() {
  const id = state.review.selectedFindingId;
  if (!id) return;
  if (!confirm("¿Eliminar este hallazgo?")) return;
  const resp = await apiFetch(`/api/findings/${id}`, { method: "DELETE" });
  if (resp.status === 204) {
    const rv = state.review;
    rv.analysis.findings = rv.analysis.findings.filter((f) => f.id !== id);
    if (state.currentAnalysis && state.currentAnalysis.id === rv.analysis.id) {
      state.currentAnalysis.findings = state.currentAnalysis.findings.filter((f) => f.id !== id);
      renderAnalysisFindings(state.currentAnalysis);
    }
    selectFinding(null);
  } else {
    alert("No se pudo eliminar: " + (await extractErrorMessage(resp)));
  }
}

function initReviewControls() {
  document.getElementById("prev-page-btn").addEventListener("click", async () => {
    if (state.review.currentPage > 1) {
      state.review.currentPage -= 1;
      await loadReviewPage();
    }
  });
  document.getElementById("next-page-btn").addEventListener("click", async () => {
    if (state.review.currentPage < state.review.document.page_count) {
      state.review.currentPage += 1;
      await loadReviewPage();
    }
  });
  document.getElementById("toggle-create-mode-btn").addEventListener("click", (e) => {
    const rv = state.review;
    rv.mode = rv.mode === "create" ? "select" : "create";
    e.target.textContent = rv.mode === "create" ? "Modo: crear anotación" : "Modo: seleccionar";
    if (rv.mode !== "create") {
      rv.pendingCreateRectPx = null;
      document.getElementById("create-finding-form").hidden = true;
    }
    selectFinding(null);
  });
  document.getElementById("save-status-btn").addEventListener("click", async () => {
    const id = state.review.selectedFindingId;
    if (!id) return;
    const status = document.getElementById("finding-status-select").value;
    const resp = await apiJson(`/api/findings/${id}`, "PATCH", { status, recalculate: false });
    if (resp.ok) {
      const updated = await resp.json();
      replaceFindingInState(updated);
      renderFindingDetail(updated);
      redrawCanvas();
    } else {
      alert("No se pudo guardar el estado: " + (await extractErrorMessage(resp)));
    }
  });
  document.getElementById("delete-finding-btn").addEventListener("click", deleteSelectedFinding);

  document.getElementById("confirm-create-finding-btn").addEventListener("click", async () => {
    const rv = state.review;
    if (!rv.pendingCreateRectPx) return;
    const ruleId = document.getElementById("create-finding-rule-select").value;
    if (!ruleId) {
      alert("Selecciona una regla.");
      return;
    }
    const canvas = document.getElementById("review-canvas");
    const bboxPt = pxRectToBboxPt(rv.pendingCreateRectPx, canvas);
    const resp = await apiJson("/api/findings", "POST", {
      analysis_id: rv.analysis.id,
      rule_id: ruleId,
      page: rv.currentPage,
      bbox: bboxPt,
    });
    if (resp.ok) {
      const created = await resp.json();
      rv.pendingCreateRectPx = null;
      document.getElementById("create-finding-form").hidden = true;
      replaceFindingInState(created);
      selectFinding(created.id);
    } else {
      alert("No se pudo crear el hallazgo: " + (await extractErrorMessage(resp)));
    }
  });

  document.getElementById("cancel-create-finding-btn").addEventListener("click", () => {
    state.review.pendingCreateRectPx = null;
    document.getElementById("create-finding-form").hidden = true;
    document.getElementById("finding-detail-empty").hidden = false;
    redrawCanvas();
  });
}

// ---------------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------------
async function loadAuthInfo() {
  const badge = document.getElementById("auth-badge");
  authMode = badge.dataset.authMode || "local";
  try {
    const resp = await apiFetch("/auth/me");
    if (resp.ok) {
      const user = await resp.json();
      document.getElementById("user-email").textContent = user.email;
    }
  } catch {
    // Silencioso: solo es un indicador informativo.
  }
}

async function init() {
  initTabs();
  initUploadForm();
  initRuleForm();
  initRuleEditor();
  initImportForms();
  initAnalysisForm();
  initCanvasInteraction();
  initReviewControls();

  await loadAuthInfo();
  await loadRules();
  await loadDocuments();
  await loadAnalysesList();
}

init();
