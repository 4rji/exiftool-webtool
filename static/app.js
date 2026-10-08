/* Metadata Cleaner - drag & drop, upload, metadata report, download */

(() => {
  "use strict";

  const THEME_STORAGE_KEY = "metadata-cleaner-theme";
  const HISTORY_STORAGE_KEY = "metadata-cleaner-result-history";
  const HISTORY_LIMIT = 50;
  const DEFAULT_THEME = "dark";

  const CATEGORY_ICONS = {
    image: "🖼️",
    pdf: "📕",
    office: "📄",
    media: "🎵",
    other: "📦",
  };

  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const browseBtn = document.getElementById("browse-btn");
  const themeToggle = document.getElementById("theme-toggle");
  const themeIcon = themeToggle.querySelector(".theme-icon");
  const progressSection = document.getElementById("progress-section");
  const progressBar = document.getElementById("progress-bar");
  const progressLabel = document.getElementById("progress-label");
  const resultsList = document.getElementById("results-list");
  const resultsEmpty = document.getElementById("results-empty");
  const clearHistoryBtn = document.getElementById("clear-history-btn");
  const backdrop = document.getElementById("backdrop");
  const reportPanel = document.getElementById("report-panel");
  const reportTitle = document.getElementById("report-title");
  const reportContent = document.getElementById("report-content");
  const reportClose = document.getElementById("report-close");
  const reportDownload = document.getElementById("report-download");

  let activeReportId = null;

  /* ---------- Theme ---------- */

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
  }

  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem(THEME_STORAGE_KEY);
    } catch {
      // Storage blocked: fall back to the default theme.
    }
    applyTheme(saved === "light" || saved === "dark" ? saved : DEFAULT_THEME);
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The toggle still works for this page view.
    }
    applyTheme(next);
  });

  /* ---------- Drag & drop / browse ---------- */

  browseBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    fileInput.click();
  });

  dropZone.addEventListener("click", () => fileInput.click());

  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      uploadFiles(fileInput.files);
      fileInput.value = "";
    }
  });

  ["dragenter", "dragover"].forEach((type) => {
    dropZone.addEventListener(type, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach((type) => {
    dropZone.addEventListener(type, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag-over");
    });
  });

  dropZone.addEventListener("drop", (event) => {
    const files = event.dataTransfer ? event.dataTransfer.files : null;
    if (files && files.length > 0) {
      uploadFiles(files);
    }
  });

  /* ---------- Upload ---------- */

  function uploadFiles(fileList) {
    const formData = new FormData();
    Array.from(fileList).forEach((file) => formData.append("files", file));

    showProgress(fileList.length);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/clean");

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setProgress(percent, percent < 100 ? `Uploading… ${percent}%` : "Removing metadata…");
      }
    });

    xhr.addEventListener("load", () => {
      hideProgress();
      let payload = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        renderUploadError("Server returned an invalid response");
        return;
      }
      if (xhr.status !== 200) {
        renderUploadError(payload.error || `Upload failed (HTTP ${xhr.status})`);
        return;
      }
      payload.files.forEach((file) => addResultItem(file));
    });

    xhr.addEventListener("error", () => {
      hideProgress();
      renderUploadError("Network error. Is the server running?");
    });

    xhr.send(formData);
  }

  function showProgress(fileCount) {
    progressSection.hidden = false;
    setProgress(0, `Uploading ${fileCount} file${fileCount > 1 ? "s" : ""}…`);
  }

  function setProgress(percent, label) {
    progressBar.style.width = `${percent}%`;
    progressLabel.textContent = label;
  }

  function hideProgress() {
    progressSection.hidden = true;
    progressBar.style.width = "0%";
  }

  /* ---------- Results list ---------- */

  function updateEmptyState() {
    const hasResults = resultsList.children.length > 0;
    resultsEmpty.hidden = hasResults;
    clearHistoryBtn.disabled = !hasResults;
  }

  function readResultHistory() {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(HISTORY_STORAGE_KEY));
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((file) => file && file.id && file.clean_name);
    } catch {
      return [];
    }
  }

  function writeResultHistory(history) {
    try {
      sessionStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.slice(-HISTORY_LIMIT)));
    } catch {
      // The app still works when browser storage is unavailable.
    }
  }

  function saveResultToHistory(file) {
    if (file.status !== "ok") return;
    const history = readResultHistory().filter((entry) => entry.id !== file.id);
    history.push({
      id: file.id,
      status: "ok",
      original_name: file.original_name,
      clean_name: file.clean_name,
      category: file.category,
      removed_count: file.removed_count,
    });
    writeResultHistory(history);
  }

  function restoreResultHistory() {
    readResultHistory().forEach((file) => addResultItem(file, { persist: false }));
  }

  function clearResultHistory() {
    try {
      sessionStorage.removeItem(HISTORY_STORAGE_KEY);
    } catch {
      // Clearing the visible list still works when browser storage is blocked.
    }
    resultsList.replaceChildren();
    closeReport();
    updateEmptyState();
  }

  clearHistoryBtn.addEventListener("click", clearResultHistory);

  function renderUploadError(message) {
    addResultItem({ original_name: "Upload", status: "error", error: message });
  }

  function removedLabel(count) {
    if (!count) return "no metadata found";
    return `${count} field${count === 1 ? "" : "s"} removed`;
  }

  function addResultItem(file, options = {}) {
    const item = document.createElement("li");
    item.className = "result-item";

    if (file.status !== "ok") {
      item.classList.add("result-error");
      const info = makeSpan("result-info", "");
      info.append(
        makeSpan("result-name", file.original_name),
        makeSpan("result-error-message", file.error || "Cleaning failed")
      );
      item.append(makeSpan("result-icon", "❌"), info);
    } else {
      const info = makeSpan("result-info", "");
      const meta = makeSpan("result-meta", "");
      meta.append(
        makeSpan(`category-chip category-${file.category}`, file.category),
        makeSpan("result-removed", removedLabel(file.removed_count))
      );
      info.append(makeSpan("result-name", file.clean_name), meta);

      const actions = document.createElement("span");
      actions.className = "result-actions";
      actions.append(
        makeViewButton(`View metadata of ${file.original_name}`, () => openReport(file.id)),
        makeDownloadButton(`Download ${file.clean_name}`, () => downloadFile(file.id))
      );

      item.dataset.fileId = file.id;
      item.title = `Original: ${file.original_name}`;
      item.append(makeSpan("result-icon", CATEGORY_ICONS[file.category] || "📦"), info, actions);
    }

    resultsList.prepend(item);
    if (options.persist !== false) {
      saveResultToHistory(file);
    }
    updateEmptyState();
  }

  function makeSpan(className, text) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    return span;
  }

  function makeDownloadButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-download";
    button.setAttribute("aria-label", label);
    button.innerHTML =
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
      "<span>Download</span>";
    button.addEventListener("click", onClick);
    return button;
  }

  function makeViewButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-view";
    button.setAttribute("aria-label", label);
    button.innerHTML =
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
      "<span>View</span>";
    button.addEventListener("click", onClick);
    return button;
  }

  /* ---------- Download ---------- */

  function downloadFile(fileId) {
    const link = document.createElement("a");
    link.href = `/download/${encodeURIComponent(fileId)}`;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  /* ---------- Metadata report panel ---------- */

  function groupFields(fields) {
    const groups = new Map();
    fields.forEach((field) => {
      if (!groups.has(field.group)) groups.set(field.group, []);
      groups.get(field.group).push(field);
    });
    // "File" holds format facts (type, size, encoding): show the real metadata first.
    if (groups.has("File")) {
      const fileFields = groups.get("File");
      groups.delete("File");
      groups.set("File", fileFields);
    }
    return groups;
  }

  function renderReport(report) {
    reportContent.replaceChildren();

    const summary = document.createElement("div");
    summary.className = "report-summary";
    const total = report.fields.length;
    summary.append(
      makeSpan(`category-chip category-${report.category}`, report.category),
      makeSpan("report-mime", report.mime),
      makeSpan("report-count", total ? `${report.removed_count} of ${total} fields removed` : "No metadata found")
    );
    reportContent.append(summary);

    if (!total) return;

    const legend = document.createElement("p");
    legend.className = "report-legend";
    legend.textContent =
      "Metadata found in the uploaded file. “Kept” fields describe the file itself (format, size, encoding) and are needed to open it.";
    reportContent.append(legend);

    groupFields(report.fields).forEach((fields, group) => {
      const section = document.createElement("section");
      section.className = "report-group";

      const heading = document.createElement("h4");
      heading.className = "report-group-title";
      heading.textContent = group;
      section.append(heading);

      const table = document.createElement("table");
      table.className = "report-table";
      const body = document.createElement("tbody");
      fields.forEach((field) => {
        const row = document.createElement("tr");
        if (field.removed) row.className = "is-removed";

        const tag = document.createElement("th");
        tag.scope = "row";
        tag.textContent = field.tag;

        const value = document.createElement("td");
        value.className = "report-value";
        value.textContent = field.value;

        const status = document.createElement("td");
        status.className = "report-status";
        status.append(makeSpan(field.removed ? "status-chip status-removed" : "status-chip status-kept", field.removed ? "removed" : "kept"));

        row.append(tag, value, status);
        body.append(row);
      });
      table.append(body);
      section.append(table);
      reportContent.append(section);
    });
  }

  function showPanel() {
    backdrop.hidden = false;
    reportPanel.classList.add("open");
    reportPanel.setAttribute("aria-hidden", "false");
    reportContent.scrollTop = 0;
    reportClose.focus();
  }

  async function openReport(fileId) {
    activeReportId = fileId;
    reportTitle.textContent = "Loading…";
    reportContent.replaceChildren();
    reportDownload.disabled = true;
    showPanel();
    try {
      const response = await fetch(`/metadata/${encodeURIComponent(fileId)}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || `Report unavailable (HTTP ${response.status})`);
      }
      if (activeReportId !== fileId) return;
      reportTitle.textContent = payload.original_name;
      renderReport(payload);
      reportDownload.disabled = false;
    } catch (error) {
      if (activeReportId !== fileId) return;
      reportTitle.textContent = "Metadata report";
      reportContent.replaceChildren(makeSpan("report-error", error.message));
    }
  }

  function closeReport() {
    reportPanel.classList.remove("open");
    reportPanel.setAttribute("aria-hidden", "true");
    backdrop.hidden = true;
    activeReportId = null;
  }

  reportClose.addEventListener("click", closeReport);
  backdrop.addEventListener("click", closeReport);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeReportId !== null) {
      closeReport();
    }
  });

  reportDownload.addEventListener("click", () => {
    if (activeReportId === null) return;
    downloadFile(activeReportId);
  });

  /* ---------- Init ---------- */

  initTheme();
  restoreResultHistory();
  updateEmptyState();
})();
