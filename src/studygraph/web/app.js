const state = {
  documents: [],
  selectedDocumentId: null,
};

const elements = {
  chunkList: document.querySelector("#chunk-list"),
  deleteButton: document.querySelector("#delete-button"),
  documentCount: document.querySelector("#document-count"),
  documentDetail: document.querySelector("#document-detail"),
  documentList: document.querySelector("#document-list"),
  healthStatus: document.querySelector("#health-status"),
  notice: document.querySelector("#notice"),
  pdfInput: document.querySelector("#pdf-input"),
  refreshButton: document.querySelector("#refresh-button"),
  searchCount: document.querySelector("#search-count"),
  searchForm: document.querySelector("#search-form"),
  searchInput: document.querySelector("#search-input"),
  searchResults: document.querySelector("#search-results"),
  selectedFileName: document.querySelector("#selected-file-name"),
  uploadButton: document.querySelector("#upload-button"),
  uploadForm: document.querySelector("#upload-form"),
  uploadState: document.querySelector("#upload-state"),
};

class ApiError extends Error {
  constructor(status, body) {
    super(`Request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }

  return body;
}

function getErrorMessage(error) {
  if (error instanceof ApiError) {
    const detail = error.body?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (detail?.message) {
      return detail.message;
    }
  }

  return "Request failed.";
}

function showNotice(message, variant = "") {
  elements.notice.textContent = message;
  elements.notice.className = variant ? `notice ${variant}` : "notice";
}

function setUploadState(label, statusClass) {
  elements.uploadState.textContent = label;
  elements.uploadState.className = `status-badge ${statusClass}`;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function getStatusClass(status) {
  if (["failed", "pending", "processed"].includes(status)) {
    return `status-${status}`;
  }

  return "status-idle";
}

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = text;
  return element;
}

async function refreshHealth() {
  try {
    const health = await requestJson("/health");
    elements.healthStatus.textContent = health.database_configured
      ? "API online, database configured"
      : "API online, database not configured";
  } catch {
    elements.healthStatus.textContent = "API status unavailable";
  }
}

async function refreshDocuments() {
  const documentList = await requestJson("/documents?limit=100");
  state.documents = documentList.items;
  elements.documentCount.textContent = `${formatNumber(documentList.total)} stored`;
  renderDocuments();

  if (
    state.selectedDocumentId !== null &&
    !state.documents.some((documentItem) => documentItem.id === state.selectedDocumentId)
  ) {
    clearSelection();
  }
}

function renderDocuments() {
  elements.documentList.replaceChildren();

  if (state.documents.length === 0) {
    elements.documentList.append(
      createTextElement("div", "empty-state", "No documents stored")
    );
    return;
  }

  for (const documentItem of state.documents) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      documentItem.id === state.selectedDocumentId
        ? "document-item active"
        : "document-item";
    button.addEventListener("click", () => selectDocument(documentItem.id));

    const title = createTextElement("div", "item-title", documentItem.filename);
    const meta = createTextElement(
      "div",
      "item-meta",
      `${formatNumber(documentItem.character_count)} chars | ${documentItem.page_count} pages`
    );
    const statusBadge = createTextElement(
      "span",
      `status-badge ${getStatusClass(documentItem.status)}`,
      documentItem.status
    );

    button.append(title, meta, statusBadge);
    elements.documentList.append(button);
  }
}

function clearSelection() {
  state.selectedDocumentId = null;
  elements.deleteButton.disabled = true;
  elements.documentDetail.className = "document-detail empty-state";
  elements.documentDetail.textContent = "No document selected";
  elements.chunkList.replaceChildren();
  renderDocuments();
}

async function selectDocument(documentId) {
  state.selectedDocumentId = documentId;
  elements.deleteButton.disabled = false;
  renderDocuments();

  const [documentItem, chunkList] = await Promise.all([
    requestJson(`/documents/${documentId}`),
    requestJson(`/documents/${documentId}/chunks`),
  ]);

  renderDocumentDetail(documentItem);
  renderChunks(chunkList.items);
}

function renderDocumentDetail(documentItem) {
  elements.documentDetail.className = "document-detail";
  elements.documentDetail.replaceChildren();

  const title = createTextElement("div", "detail-title", documentItem.filename);
  const statusBadge = createTextElement(
    "span",
    `status-badge ${getStatusClass(documentItem.status)}`,
    documentItem.status
  );
  const metaGrid = document.createElement("div");
  metaGrid.className = "meta-grid";

  const rows = [
    ["Pages", formatNumber(documentItem.page_count)],
    ["Characters", formatNumber(documentItem.character_count)],
    ["File size", `${formatNumber(documentItem.file_size_bytes)} bytes`],
    ["Created", formatDate(documentItem.created_at)],
  ];

  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "meta-row";
    row.append(
      createTextElement("span", "", label),
      createTextElement("strong", "", value)
    );
    metaGrid.append(row);
  }

  elements.documentDetail.append(title, statusBadge, metaGrid);

  if (documentItem.processing_error) {
    elements.documentDetail.append(
      createTextElement("p", "notice error", documentItem.processing_error)
    );
  }
}

function renderChunks(chunks) {
  elements.chunkList.replaceChildren();

  if (chunks.length === 0) {
    elements.chunkList.append(createTextElement("div", "empty-state", "No chunks"));
    return;
  }

  for (const chunk of chunks) {
    const item = document.createElement("article");
    item.className = "chunk-item";
    const header = createTextElement(
      "div",
      "chunk-header",
      `Chunk ${chunk.position + 1} | ${formatNumber(chunk.character_count)} chars`
    );
    const text = createTextElement("div", "chunk-text", chunk.text);
    item.append(header, text);
    elements.chunkList.append(item);
  }
}

async function handleUpload(event) {
  event.preventDefault();

  const file = elements.pdfInput.files[0];

  if (!file) {
    showNotice("Select a PDF first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  elements.uploadButton.disabled = true;
  setUploadState("Uploading", "status-pending");
  showNotice("");

  try {
    const documentItem = await requestJson("/documents", {
      method: "POST",
      body: formData,
    });
    state.selectedDocumentId = documentItem.id;
    showNotice("Upload processed.", "success");
    setUploadState("Processed", "status-processed");
    elements.uploadForm.reset();
    elements.selectedFileName.textContent = "Select PDF";
    await refreshDocuments();
    await selectDocument(documentItem.id);
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
    setUploadState("Failed", "status-failed");
    await refreshDocuments().catch(() => undefined);
  } finally {
    elements.uploadButton.disabled = false;
  }
}

async function handleSearch(event) {
  event.preventDefault();
  const query = elements.searchInput.value.trim();

  if (!query) {
    elements.searchCount.textContent = "0 results";
    elements.searchResults.replaceChildren();
    return;
  }

  try {
    const searchResult = await requestJson(
      `/search?query=${encodeURIComponent(query)}&limit=20`
    );
    elements.searchCount.textContent = `${formatNumber(searchResult.total)} results`;
    renderSearchResults(searchResult.items);
  } catch (error) {
    elements.searchCount.textContent = "0 results";
    elements.searchResults.replaceChildren(
      createTextElement("div", "empty-state", getErrorMessage(error))
    );
  }
}

function renderSearchResults(results) {
  elements.searchResults.replaceChildren();

  if (results.length === 0) {
    elements.searchResults.append(
      createTextElement("div", "empty-state", "No matching chunks")
    );
    return;
  }

  for (const result of results) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-item";
    button.addEventListener("click", () => selectDocument(result.document_id));
    button.append(
      createTextElement("div", "item-title", result.document_filename),
      createTextElement(
        "div",
        "item-meta",
        `Chunk ${result.chunk_position + 1} | ${formatNumber(result.character_count)} chars`
      ),
      createTextElement("div", "result-snippet", result.snippet)
    );
    elements.searchResults.append(button);
  }
}

async function handleDelete() {
  if (state.selectedDocumentId === null) {
    return;
  }

  const documentId = state.selectedDocumentId;
  elements.deleteButton.disabled = true;

  try {
    await fetch(`/documents/${documentId}`, { method: "DELETE" });
    clearSelection();
    await refreshDocuments();
    showNotice("Document deleted.", "success");
  } catch (error) {
    elements.deleteButton.disabled = false;
    showNotice(getErrorMessage(error), "error");
  }
}

elements.uploadForm.addEventListener("submit", handleUpload);
elements.searchForm.addEventListener("submit", handleSearch);
elements.refreshButton.addEventListener("click", async () => {
  await refreshHealth();
  await refreshDocuments().catch((error) => showNotice(getErrorMessage(error), "error"));
});
elements.deleteButton.addEventListener("click", handleDelete);
elements.pdfInput.addEventListener("change", () => {
  elements.selectedFileName.textContent =
    elements.pdfInput.files[0]?.name ?? "Select PDF";
});

refreshHealth();
refreshDocuments().catch((error) => showNotice(getErrorMessage(error), "error"));
