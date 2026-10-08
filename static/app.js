/* Markdown Converter - drag & drop, upload, preview, download */

(() => {
  "use strict";

  const THEME_STORAGE_KEY = "markdown-converter-theme";
  const HISTORY_STORAGE_KEY = "markdown-converter-result-history";
  const HISTORY_LIMIT = 50;
  const DEFAULT_THEME = "dark";

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
  const previewPanel = document.getElementById("preview-panel");
  const previewTitle = document.getElementById("preview-title");
  const previewContent = document.getElementById("preview-content");
  const previewClose = document.getElementById("preview-close");
  const previewCopy = document.getElementById("preview-copy");
  const previewDownload = document.getElementById("preview-download");
  const transcriptionSettings = document.getElementById("transcription-settings");
  const selectedFilesSummary = document.getElementById("selected-files-summary");
  const cancelSelection = document.getElementById("cancel-selection");
  const convertFilesBtn = document.getElementById("convert-files-btn");
  const languageSelect = document.getElementById("transcription-language");
  const contextInput = document.getElementById("transcription-context");
  const contextHelp = document.getElementById("context-help");
  const timestampsInput = document.getElementById("include-timestamps");
  const timestampsHelp = document.getElementById("timestamps-help");
  const localEngine = document.getElementById("local-engine");
  const localEngineOption = document.getElementById("local-engine-option");
  const localStatusLabel = document.getElementById("local-status-label");
  const localUnavailableReason = document.getElementById("local-unavailable-reason");

  const MEDIA_EXTENSIONS = new Set(["mp3", "wav", "m4a", "aac", "flac", "ogg", "webm", "mp4"]);
  let pendingFiles = [];

  let activePreviewId = null;
  let activePreviewMarkdown = "";
  const copyResetTimers = new WeakMap();

  /* ---------- Theme ---------- */

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    applyTheme(saved === "light" || saved === "dark" ? saved : DEFAULT_THEME);
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_STORAGE_KEY, next);
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
      selectFiles(fileInput.files);
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
      selectFiles(files);
    }
  });

  /* ---------- Upload ---------- */

  function containsMedia(files) {
    return files.some((file) => MEDIA_EXTENSIONS.has((file.name.split(".").pop() || "").toLowerCase()));
  }

  function selectFiles(fileList) {
    const files = Array.from(fileList);
    if (!containsMedia(files)) {
      uploadFiles(files);
      return;
    }
    pendingFiles = files;
    const mediaCount = files.filter((file) => containsMedia([file])).length;
    selectedFilesSummary.textContent = `${files.length} file${files.length === 1 ? "" : "s"} selected · ${mediaCount} audio/video`;
    transcriptionSettings.hidden = false;
    transcriptionSettings.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function selectedEngine() {
    return document.querySelector('input[name="transcription-engine"]:checked').value;
  }

  function updateTimestampControl() {
    const engine = selectedEngine();
    timestampsInput.disabled = engine === "openai";
    if (engine === "openai") timestampsInput.checked = false;
    if (engine === "openai_diarize") timestampsInput.checked = true;
    timestampsHelp.textContent = engine === "openai" ? "Not available for GPT-4o Transcribe" : "Add [HH:MM:SS] to transcript segments";
    contextInput.disabled = engine === "openai_diarize";
    contextHelp.textContent = engine === "openai_diarize" ? "(not supported by diarization)" : "(optional)";
  }

  document.querySelectorAll('input[name="transcription-engine"]').forEach((input) => {
    input.addEventListener("change", updateTimestampControl);
  });

  cancelSelection.addEventListener("click", () => {
    pendingFiles = [];
    transcriptionSettings.hidden = true;
  });

  convertFilesBtn.addEventListener("click", () => {
    if (!pendingFiles.length) return;
    const files = pendingFiles;
    pendingFiles = [];
    transcriptionSettings.hidden = true;
    uploadFiles(files, {
      engine: selectedEngine(),
      language: languageSelect.value,
      context: contextInput.value,
      timestamps: timestampsInput.checked,
    });
  });

  function uploadFiles(fileList, transcription = null) {
    const formData = new FormData();
    Array.from(fileList).forEach((file) => formData.append("files", file));
    if (transcription) {
      formData.append("transcription_engine", transcription.engine);
      formData.append("transcription_language", transcription.language);
      formData.append("transcription_context", transcription.context);
      formData.append("include_timestamps", String(transcription.timestamps));
    }

    showProgress(fileList.length);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/convert");

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setProgress(percent, percent < 100 ? `Uploading… ${percent}%` : "Converting…");
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
      payload.files.forEach(addResultItem);
    });

    xhr.addEventListener("error", () => {
      hideProgress();
      renderUploadError("Network error — is the server running?");
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
      return parsed.filter((file) => file && file.id && file.md_name);
    } catch {
      return [];
    }
  }

  function writeResultHistory(history) {
    try {
      sessionStorage.setItem(
        HISTORY_STORAGE_KEY,
        JSON.stringify(history.slice(-HISTORY_LIMIT))
      );
    } catch {
      // The app still works when browser storage is unavailable.
    }
  }

  function saveResultToHistory(file) {
    if (file.status !== "ok") return;
    const history = readResultHistory().filter((entry) => entry.id !== file.id);
    history.push({
      id: file.id,
      md_name: file.md_name,
      status: "ok",
    });
    writeResultHistory(history);
  }

  function restoreResultHistory() {
    readResultHistory()
      .slice()
      .reverse()
      .forEach((file) => addResultItem(file, { persist: false }));
  }

  function clearResultHistory() {
    try {
      sessionStorage.removeItem(HISTORY_STORAGE_KEY);
    } catch {
      // Clearing the visible list still works when browser storage is blocked.
    }
    resultsList.replaceChildren();
    closePreview();
    updateEmptyState();
  }

  clearHistoryBtn.addEventListener("click", clearResultHistory);

  function renderUploadError(message) {
    addResultItem({
      id: null,
      original_name: "Upload",
      md_name: null,
      status: "error",
      error: message,
    });
  }

  function addResultItem(file, options = {}) {
    const item = document.createElement("li");
    item.className = "result-item";

    if (file.status !== "ok") {
      item.classList.add("result-error");
      item.append(
        makeSpan("result-icon", "❌"),
        makeSpan("result-name", file.original_name),
        makeSpan("result-error-message", file.error || "Conversion failed")
      );
    } else {
      const previewBtn = makeViewButton(`Preview ${file.md_name}`, () =>
        openPreview(file.id, file.md_name)
      );
      const copyBtn = makeCopyButton(`Copy ${file.md_name}`, (event) =>
        copyFile(file.id, event.currentTarget)
      );
      const downloadBtn = makeDownloadButton(`Download ${file.md_name}`, () =>
        downloadFile(file.id)
      );
      const actions = document.createElement("span");
      actions.className = "result-actions";
      actions.append(previewBtn, copyBtn, downloadBtn);
      item.dataset.fileId = file.id;
      item.append(
        makeSpan("result-icon", "📄"),
        makeSpan("result-name", file.md_name),
        actions
      );
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

  function makeCopyButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-copy";
    button.setAttribute("aria-label", label);
    button.innerHTML =
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
      "<span data-button-label>Copy</span>";
    button.addEventListener("click", onClick);
    return button;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();

    try {
      if (!document.execCommand("copy")) {
        throw new Error("Copy command failed");
      }
    } finally {
      textarea.remove();
    }
  }

  function setCopyStatus(button, text) {
    if (!button) return;
    const label = button.querySelector("[data-button-label]");
    if (!label) return;

    if (!button.dataset.defaultCopyLabel) {
      button.dataset.defaultCopyLabel = label.textContent;
    }
    if (copyResetTimers.has(button)) {
      window.clearTimeout(copyResetTimers.get(button));
      copyResetTimers.delete(button);
    }

    label.textContent = text;
    button.disabled = text === "Copying";
    if (text === "Copying") return;

    const defaultLabel = button.dataset.defaultCopyLabel;
    const resetTimer = window.setTimeout(() => {
      label.textContent = defaultLabel;
      button.disabled = false;
      copyResetTimers.delete(button);
    }, 1400);

    copyResetTimers.set(button, resetTimer);
  }

  async function copyFile(fileId, button) {
    setCopyStatus(button, "Copying");
    try {
      let markdown = "";
      if (activePreviewId === fileId && activePreviewMarkdown) {
        markdown = activePreviewMarkdown;
      } else {
        const response = await fetch(`/preview/${encodeURIComponent(fileId)}`);
        if (!response.ok) {
          throw new Error(`Copy unavailable (HTTP ${response.status})`);
        }
        markdown = await response.text();
      }
      await copyText(markdown);
      setCopyStatus(button, "Copied");
    } catch {
      setCopyStatus(button, "Failed");
    }
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

  /* ---------- Preview panel ---------- */

  function renderMarkdownPage(markdown) {
    previewContent.innerHTML = "";
    const page = document.createElement("div");
    page.className = "md-page";

    if (window.marked && window.DOMPurify) {
      const rawHtml = window.marked.parse(markdown, { breaks: true });
      page.innerHTML = window.DOMPurify.sanitize(rawHtml);
    } else {
      page.textContent = markdown;
      page.classList.add("md-page-plain");
    }

    previewContent.appendChild(page);
    previewContent.scrollTop = 0;
  }

  async function openPreview(fileId, mdName) {
    try {
      const response = await fetch(`/preview/${encodeURIComponent(fileId)}`);
      if (!response.ok) {
        throw new Error(`Preview unavailable (HTTP ${response.status})`);
      }
      const markdown = await response.text();
      previewTitle.textContent = mdName;
      renderMarkdownPage(markdown);
      activePreviewId = fileId;
      activePreviewMarkdown = markdown;
      backdrop.hidden = false;
      previewPanel.classList.add("open");
      previewPanel.setAttribute("aria-hidden", "false");
    } catch (error) {
      previewTitle.textContent = mdName;
      previewContent.textContent = error.message;
      activePreviewId = null;
      activePreviewMarkdown = "";
      backdrop.hidden = false;
      previewPanel.classList.add("open");
      previewPanel.setAttribute("aria-hidden", "false");
    }
  }

  function closePreview() {
    previewPanel.classList.remove("open");
    previewPanel.setAttribute("aria-hidden", "true");
    backdrop.hidden = true;
    activePreviewId = null;
    activePreviewMarkdown = "";
  }

  previewClose.addEventListener("click", closePreview);
  backdrop.addEventListener("click", closePreview);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activePreviewId !== null) {
      closePreview();
    }
  });

  previewDownload.addEventListener("click", () => {
    if (activePreviewId === null) return;
    downloadFile(activePreviewId);
  });

  previewCopy.addEventListener("click", (event) => {
    if (activePreviewId === null) return;
    copyFile(activePreviewId, event.currentTarget);
  });

  /* ---------- Init ---------- */

  async function loadTranscriptionStatus() {
    try {
      const response = await fetch("/api/transcription/status");
      if (!response.ok) throw new Error();
      const status = await response.json();
      localEngine.disabled = !status.local.available;
      localEngineOption.classList.toggle("engine-unavailable", !status.local.available);
      localStatusLabel.textContent = status.local.available ? "Private / Offline" : "Unavailable";
      localUnavailableReason.textContent = status.local.unavailable_reason || "";
    } catch {
      localEngine.disabled = true;
      localEngineOption.classList.add("engine-unavailable");
      localStatusLabel.textContent = "Unavailable";
      localUnavailableReason.textContent = "Status check failed";
    }
  }

  initTheme();
  updateTimestampControl();
  loadTranscriptionStatus();
  restoreResultHistory();
  updateEmptyState();
})();
