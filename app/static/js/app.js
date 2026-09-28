const state = {
  uploadId: null,
  filename: null,
  columns: [],
  resultId: null,
  preview: null,
  exportFormat: "csv",
};

const operations = [
  ["trim_whitespace", "Trim whitespace"],
  ["drop_duplicates", "Remove duplicate rows"],
  ["drop_empty_rows", "Drop empty rows"],
  ["rename_column", "Rename column"],
  ["fill_missing", "Fill missing values"],
  ["lowercase", "Lowercase text"],
  ["uppercase", "Uppercase text"],
  ["normalize_dates", "Normalize dates"],
  ["convert_numeric", "Convert to number"],
  ["filter_rows", "Filter rows"],
];
const MULTI_COLUMN_SCOPE = "__flowforge_multi_column_scope__";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("is-error", error);
  el.classList.add("is-visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("is-visible"), 3400);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try { message = (await response.json()).detail || message; } catch (_) { /* empty */ }
    throw new Error(Array.isArray(message) ? message[0]?.msg : message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function goTo(step) {
  $$(".panel").forEach((panel) => panel.classList.toggle("is-visible", panel.id === `panel-${step}`));
  const ordered = ["upload", "recipe", "preview", "export"];
  const active = ordered.indexOf(step);
  $$(".step").forEach((button, index) => {
    button.classList.toggle("is-active", index === active);
    button.classList.toggle("is-done", index < active);
    button.setAttribute("aria-current", index === active ? "step" : "false");
  });
}

async function handleFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  $("#dropzone").classList.add("is-loading");
  try {
    const data = await api("/api/uploads", { method: "POST", body: form });
    state.uploadId = data.upload_id;
    state.filename = data.filename;
    state.columns = data.columns;
    state.resultId = null;
    state.preview = null;
    $("#file-name").textContent = data.filename;
    $("#file-meta").textContent = `${data.total_rows.toLocaleString()} rows · ${data.columns.length} columns`;
    $("#file-type").textContent = data.filename.split(".").pop().toUpperCase();
    $("#dropzone").hidden = true;
    $("#file-card").hidden = false;
    $("#to-recipe").disabled = false;
    refreshAllColumnSelects();
    toast("Source file loaded and profiled.");
  } catch (error) { toast(error.message, true); }
  finally { $("#dropzone").classList.remove("is-loading"); }
}

function optionsHtml(values, selected = "") {
  const selectedValues = Array.isArray(selected) ? selected : [selected];
  return values.map((value) => `<option value="${escapeHtml(value)}" ${selectedValues.includes(value) ? "selected" : ""}>${escapeHtml(value)}</option>`).join("");
}

function field(label, className, content, type = "select") {
  if (type === "input") {
    return `<div class="rule-field"><label>${label}</label><input class="${className}" value="${content}"></div>`;
  }
  return `<div class="rule-field"><label>${label}</label><select class="${className}">${content}</select></div>`;
}

function updateFilterValueVisibility(row) {
  const operator = $(".operator-select", row)?.value;
  const valueField = $(".value", row)?.closest(".rule-field");
  if (valueField) valueField.hidden = ["is_empty", "is_not_empty"].includes(operator);
}

function renderRuleOptions(row, operation, values = {}) {
  const target = $(".rule-options", row);
  const columnOptions = optionsHtml(state.columns, values.column || "");
  const selectedColumns = values.columns || [];
  const multipleScope = selectedColumns.length > 1
    ? `<option value="${MULTI_COLUMN_SCOPE}" selected>${selectedColumns.length} selected columns</option>`
    : "";
  const selectedColumn = selectedColumns.length === 1 ? selectedColumns : [];
  const allColumns = `<option value="" ${selectedColumns.length ? "" : "selected"}>All compatible columns</option>${multipleScope}${optionsHtml(state.columns, selectedColumn)}`;
  const invalidOptions = optionsHtml(["empty", "drop", "keep"], values.invalid || "empty");
  let html = "";

  if (["rename_column", "fill_missing", "normalize_dates", "convert_numeric", "filter_rows"].includes(operation)) {
    html += field("COLUMN", "column-select", columnOptions);
  } else if (["trim_whitespace", "lowercase", "uppercase", "drop_duplicates", "drop_empty_rows"].includes(operation)) {
    html += field("SCOPE", "columns-select", allColumns);
  }
  if (operation === "rename_column") html += field("NEW NAME", "new-name", escapeHtml(values.new_name || ""), "input");
  if (operation === "fill_missing") html += field("VALUE", "value", escapeHtml(values.value ?? ""), "input");
  if (["normalize_dates", "convert_numeric"].includes(operation)) html += field("ON INVALID", "invalid-select", invalidOptions);
  if (operation === "normalize_dates") html += field("FORMAT", "date-format", escapeHtml(values.date_format || "%Y-%m-%d"), "input");
  if (operation === "drop_empty_rows") html += field("MATCH", "how-select", optionsHtml(["all", "any"], values.how || "all"));
  if (operation === "filter_rows") {
    const operators = ["equals", "not_equals", "contains", "not_contains", "greater_than", "greater_or_equal", "less_than", "less_or_equal", "is_empty", "is_not_empty"];
    html += field("CONDITION", "operator-select", optionsHtml(operators, values.operator || "equals"));
    html += field("VALUE", "value", escapeHtml(values.value ?? ""), "input");
  }
  target.innerHTML = html;
  const scopeSelect = $(".columns-select", row);
  if (scopeSelect) scopeSelect.dataset.columns = JSON.stringify(selectedColumns);
  $(".operator-select", row)?.addEventListener("change", () => updateFilterValueVisibility(row));
  updateFilterValueVisibility(row);
}

function addRule(values = {}) {
  const row = $("#rule-template").content.firstElementChild.cloneNode(true);
  const select = $(".operation-select", row);
  select.innerHTML = optionsHtml(operations.map(([value]) => value), values.type || "trim_whitespace");
  operations.forEach(([value, label]) => { select.querySelector(`option[value="${value}"]`).textContent = label; });
  select.addEventListener("change", () => renderRuleOptions(row, select.value));
  $(".remove-rule", row).addEventListener("click", () => { row.remove(); renumberRules(); });
  renderRuleOptions(row, select.value, values);
  $("#rule-list").append(row);
  renumberRules();
}

function renumberRules() {
  $$(".rule-row").forEach((row, index) => $(".rule-number", row).textContent = String(index + 1).padStart(2, "0"));
}

function refreshAllColumnSelects() {
  $$(".rule-row").forEach((row) => {
    const operation = $(".operation-select", row).value;
    const current = readRule(row);
    renderRuleOptions(row, operation, current);
  });
}

function readRule(row) {
  const value = (selector) => $(selector, row)?.value;
  const operation = { type: value(".operation-select") };
  if (value(".column-select")) operation.column = value(".column-select");
  const scopeSelect = $(".columns-select", row);
  if (scopeSelect?.value === MULTI_COLUMN_SCOPE) {
    operation.columns = JSON.parse(scopeSelect.dataset.columns);
  } else if (scopeSelect?.value) {
    operation.columns = [scopeSelect.value];
  }
  if (value(".new-name")) operation.new_name = value(".new-name");
  if ($(".value", row) && value(".value") !== "") operation.value = value(".value");
  if (value(".invalid-select")) operation.invalid = value(".invalid-select");
  if (value(".date-format")) operation.date_format = value(".date-format");
  if (value(".how-select")) operation.how = value(".how-select");
  if (value(".operator-select")) operation.operator = value(".operator-select");
  return operation;
}

const currentOperations = () => $$(".rule-row").map(readRule);

async function loadRecipes() {
  try {
    const recipes = await api("/api/recipes");
    const select = $("#saved-recipes");
    const current = select.value;
    select.innerHTML = '<option value="">New recipe</option>' + recipes.map((recipe) => `<option value="${recipe.id}">${escapeHtml(recipe.name)} · ${recipe.operations.length} steps</option>`).join("");
    select.value = current;
  } catch (error) { toast(error.message, true); }
}

async function selectRecipe(id) {
  if (!id) {
    $("#recipe-name").value = "";
    setDefaultRules();
    return;
  }
  try {
    const recipe = await api(`/api/recipes/${id}`);
    $("#rule-list").innerHTML = "";
    recipe.operations.forEach(addRule);
    $("#recipe-name").value = recipe.name;
    toast(`Loaded “${recipe.name}”.`);
  } catch (error) { toast(error.message, true); }
}

async function saveRecipe() {
  const name = $("#recipe-name").value.trim();
  if (!name) return toast("Give this recipe a name first.", true);
  if (!currentOperations().length) return toast("Add at least one transformation.", true);
  try {
    const recipe = await api("/api/recipes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: `Reusable ${name} workflow`, operations: currentOperations() }),
    });
    await loadRecipes();
    $("#saved-recipes").value = recipe.id;
    toast("Recipe saved to this workspace.");
  } catch (error) { toast(error.message, true); }
}

async function runPreview() {
  if (!state.uploadId) return toast("Upload a source file first.", true);
  const rules = currentOperations();
  if (!rules.length) return toast("Add at least one transformation.", true);
  const button = $("#run-preview");
  button.classList.add("is-loading");
  button.textContent = "Processing…";
  try {
    const data = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: state.uploadId, operations: rules }),
    });
    state.resultId = data.result_id;
    state.preview = data;
    renderStats(data.stats);
    renderTable(data.after);
    $$(".compare-tabs button").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.table === "after"));
    goTo("preview");
    loadJobs();
  } catch (error) { toast(error.message, true); }
  finally { button.classList.remove("is-loading"); button.innerHTML = "Run preview <span>→</span>"; }
}

function renderStats(stats) {
  const items = [
    ["INPUT ROWS", stats.input_rows],
    ["OUTPUT ROWS", stats.output_rows],
    ["DUPLICATES REMOVED", stats.duplicates_removed, stats.duplicates_removed ? "accent" : ""],
    ["EMPTY ROWS REMOVED", stats.empty_rows_removed, stats.empty_rows_removed ? "accent" : ""],
    ["INVALID ROWS", stats.invalid_rows, stats.invalid_rows ? "accent" : ""],
    ["CHANGED CELLS", stats.changed_cells],
  ];
  $("#stats-grid").innerHTML = items.map(([label, value, cls = ""]) => `<div class="stat"><span>${label}</span><strong class="${cls}">${Number.isInteger(value) ? value.toLocaleString() : value}</strong></div>`).join("");
}

function renderTable(dataset) {
  $("#preview-head").innerHTML = `<tr>${dataset.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  $("#preview-body").innerHTML = dataset.rows.map((row) => `<tr>${dataset.columns.map((column) => `<td title="${escapeHtml(row[column])}">${escapeHtml(row[column]) || "—"}</td>`).join("")}</tr>`).join("");
}

async function downloadExport() {
  if (!state.resultId) return;
  try {
    const response = await fetch("/api/exports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result_id: state.resultId, format: state.exportFormat }),
    });
    if (!response.ok) throw new Error((await response.json()).detail);
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `flowforge-${(state.filename || "export").replace(/\.[^.]+$/, "")}.${state.exportFormat}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    toast("Export downloaded.");
  } catch (error) { toast(error.message, true); }
}

async function loadJobs() {
  try {
    const jobs = await api("/api/jobs?limit=5");
    $("#job-list").innerHTML = jobs.length ? jobs.map((job) => {
      const date = new Date(`${job.created_at}Z`).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
      const rows = job.stats.output_rows == null ? "No output" : `${job.stats.output_rows.toLocaleString()} rows out`;
      return `<div class="job-row"><div class="job-name"><strong>${escapeHtml(job.input_filename)}</strong><small>${date}</small></div><span class="job-count">${rows}</span><span class="job-state ${job.status}" title="${escapeHtml(job.error_message || "")}">${job.status.toUpperCase()}</span></div>`;
    }).join("") : '<div class="empty-state">No jobs yet. Your completed runs will appear here.</div>';
  } catch (_) { /* dashboard remains usable */ }
}

function reset() {
  Object.assign(state, { uploadId: null, filename: null, columns: [], resultId: null, preview: null, exportFormat: "csv" });
  $("#file-input").value = "";
  $("#dropzone").hidden = false;
  $("#file-card").hidden = true;
  $("#to-recipe").disabled = true;
  $("#recipe-name").value = "";
  $("#saved-recipes").value = "";
  setDefaultRules();
  selectExportFormat("csv");
  goTo("upload");
}

function setDefaultRules() {
  $("#rule-list").innerHTML = "";
  addRule({ type: "trim_whitespace" });
  addRule({ type: "drop_duplicates" });
}

function selectExportFormat(format) {
  state.exportFormat = format;
  $$(".format-option").forEach((item) => {
    const selected = item.dataset.format === format;
    item.classList.toggle("is-selected", selected);
    item.setAttribute("aria-pressed", String(selected));
    $("i", item).textContent = selected ? "●" : "○";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setDefaultRules();
  loadRecipes();
  loadJobs();

  $("#file-input").addEventListener("change", (event) => handleFile(event.target.files[0]));
  const dropzone = $("#dropzone");
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("is-dragging"); }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("is-dragging"); }));
  dropzone.addEventListener("drop", (event) => handleFile(event.dataTransfer.files[0]));
  $("#to-recipe").addEventListener("click", () => goTo("recipe"));
  $("#add-rule").addEventListener("click", () => addRule());
  $("#saved-recipes").addEventListener("change", (event) => selectRecipe(event.target.value));
  $("#save-recipe").addEventListener("click", saveRecipe);
  $("#run-preview").addEventListener("click", runPreview);
  $("#to-export").addEventListener("click", () => goTo("export"));
  $("#download").addEventListener("click", downloadExport);
  $("#new-run").addEventListener("click", reset);
  $("#refresh-jobs").addEventListener("click", loadJobs);
  $$('[data-back]').forEach((button) => button.addEventListener("click", () => goTo(button.dataset.back)));
  $$(".compare-tabs button").forEach((tab) => tab.addEventListener("click", () => {
    $$(".compare-tabs button").forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-selected", String(selected));
    });
    renderTable(state.preview[tab.dataset.table]);
  }));
  $$(".format-option").forEach((option) => option.addEventListener("click", () => selectExportFormat(option.dataset.format)));
  $$(".step").forEach((button) => button.addEventListener("click", () => {
    const target = button.dataset.stepTarget;
    if (target === "upload" || (target === "recipe" && state.uploadId) || (["preview", "export"].includes(target) && state.resultId)) goTo(target);
  }));
});
