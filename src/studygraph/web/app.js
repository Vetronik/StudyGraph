const state = {
  documents: [],
  ownerId: localStorage.getItem("studygraph.ownerId") || "local-user",
  accessToken: localStorage.getItem("studygraph.accessToken") || "",
  selectedDocumentId: null,
};
const OWNER_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._@-]{0,119}$/;

const elements = {
  chunkList: document.querySelector("#chunk-list"),
  authForm: document.querySelector("#auth-form"),
  authUsername: document.querySelector("#auth-username"),
  authPassword: document.querySelector("#auth-password"),
  registerButton: document.querySelector("#register-button"),
  logoutButton: document.querySelector("#logout-button"),
  deleteButton: document.querySelector("#delete-button"),
  documentCount: document.querySelector("#document-count"),
  documentDetail: document.querySelector("#document-detail"),
  documentList: document.querySelector("#document-list"),
  healthStatus: document.querySelector("#health-status"),
  learningOutput: document.querySelector("#learning-output"),
  learningTools: document.querySelector("#learning-tools"),
  masteryButton: document.querySelector("#mastery-button"),
  notice: document.querySelector("#notice"),
  ownerInput: document.querySelector("#owner-input"),
  pdfInput: document.querySelector("#pdf-input"),
  refreshButton: document.querySelector("#refresh-button"),
  reviewButton: document.querySelector("#review-button"),
  searchCount: document.querySelector("#search-count"),
  searchForm: document.querySelector("#search-form"),
  searchInput: document.querySelector("#search-input"),
  searchResults: document.querySelector("#search-results"),
  summaryButton: document.querySelector("#summary-button"),
  selectedFileName: document.querySelector("#selected-file-name"),
  uploadButton: document.querySelector("#upload-button"),
  uploadForm: document.querySelector("#upload-form"),
  uploadState: document.querySelector("#upload-state"),
  quizButton: document.querySelector("#quiz-button"),
};

class ApiError extends Error {
  constructor(status, body) {
    super(`Request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, withOwnerHeader(options));
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }

  return body;
}

async function requestNoContent(url, options = {}) {
  const response = await fetch(url, withOwnerHeader(options));

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body);
  }
}

function withOwnerHeader(options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.accessToken) {
    headers.set("Authorization", `Bearer ${state.accessToken}`);
  } else {
    headers.set("X-StudyGraph-User", state.ownerId);
  }

  return {
    ...options,
    headers,
  };
}

function updateAuthControls() {
  elements.logoutButton.hidden = !state.accessToken;
  elements.registerButton.hidden = Boolean(state.accessToken);
}

async function login(username, password) {
  const response = await requestJson("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  state.accessToken = response.access_token;
  localStorage.setItem("studygraph.accessToken", state.accessToken);
  state.ownerId = username;
  localStorage.setItem("studygraph.ownerId", username);
  elements.ownerInput.value = username;
  updateAuthControls();
  await refreshWorkspace();
}

async function handleLogin(event) {
  event.preventDefault();
  try {
    await login(elements.authUsername.value.trim(), elements.authPassword.value);
    showNotice("Logged in.", "success");
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
  }
}

async function handleRegister() {
  try {
    await requestJson("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: elements.authUsername.value.trim(),
        password: elements.authPassword.value,
      }),
    });
    await login(elements.authUsername.value.trim(), elements.authPassword.value);
    showNotice("Account created and logged in.", "success");
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
  }
}

function handleLogout() {
  state.accessToken = "";
  localStorage.removeItem("studygraph.accessToken");
  updateAuthControls();
  clearSelection();
  refreshWorkspace().catch(() => undefined);
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
  if (status === "processing") {
    return "status-pending";
  }

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

async function refreshWorkspace() {
  await refreshHealth();
  await refreshDocuments();
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

async function waitForDocumentProcessing(documentId) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const documentItem = await requestJson(`/documents/${documentId}`);

    if (documentItem.status !== "pending") {
      return documentItem;
    }

    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  return requestJson(`/documents/${documentId}`);
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
  elements.learningTools.hidden = true;
  elements.learningOutput.replaceChildren();
  renderDocuments();
}

async function selectDocument(documentId) {
  state.selectedDocumentId = documentId;
  elements.deleteButton.disabled = false;
  renderDocuments();

  const [documentItem, chunkList, progress] = await Promise.all([
    requestJson(`/documents/${documentId}`),
    requestJson(`/documents/${documentId}/chunks`),
    requestJson(`/documents/${documentId}/progress`),
  ]);

  renderDocumentDetail(documentItem);
  renderChunks(chunkList.items);
  renderProgress(progress);
}

function renderProgress(progress) {
  elements.learningTools.hidden = false;
  elements.masteryButton.textContent = progress.mastered
    ? "Mark not mastered"
    : "Mark mastered";
  elements.learningOutput.replaceChildren(
    createTextElement(
      "p",
      "item-meta",
      `${formatNumber(progress.review_count)} reviews${progress.last_reviewed_at ? ` | Last: ${formatDate(progress.last_reviewed_at)}` : ""}`,
    ),
  );
}

async function updateProgress(url, options) {
  try {
    const progress = await requestJson(url, options);
    renderProgress(progress);
    showNotice("Learning progress updated.", "success");
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
  }
}

async function showSummary() {
  if (state.selectedDocumentId === null) return;
  try {
    const summary = await requestJson(`/documents/${state.selectedDocumentId}/summary`);
    elements.learningOutput.replaceChildren(
      createTextElement("p", "learning-text", summary.summary),
      createTextElement("p", "item-meta", `${summary.sources.length} source(s)`),
    );
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
  }
}

async function showQuiz() {
  if (state.selectedDocumentId === null) return;
  try {
    const quiz = await requestJson(`/documents/${state.selectedDocumentId}/quiz?count=5`);
    elements.learningOutput.replaceChildren(
        ...quiz.questions.map((question, index) => {
          const item = document.createElement("article");
          item.className = "quiz-item";
        const feedback = createTextElement("div", "item-meta", "");
        const submitAnswer = async (answer) => {
          try {
            const result = await requestJson(
              `/documents/${state.selectedDocumentId}/quiz/validate`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question_index: index, answer, count: 5 }),
              },
            );
            feedback.textContent = result.correct ? "Correct" : "Try again";
            feedback.className = result.correct ? "quiz-correct" : "quiz-wrong";
          } catch (error) {
            feedback.textContent = getErrorMessage(error);
            feedback.className = "item-meta";
          }
        };
        item.append(createTextElement("strong", "", `${index + 1}. ${question.question}`));
        if (question.question_type === "multiple_choice") {
          const options = document.createElement("div");
          options.className = "quiz-options";
          for (const option of question.options) {
            const button = createTextElement("button", "icon-button", option);
            button.type = "button";
            button.addEventListener("click", () => submitAnswer(option));
            options.append(button);
          }
          item.append(options);
        } else {
          const form = document.createElement("form");
          form.className = "quiz-answer-form";
          const input = document.createElement("input");
          input.required = true;
          input.placeholder = "Your answer";
          const button = createTextElement("button", "secondary-button", "Check");
          button.type = "submit";
          form.append(input, button);
          form.addEventListener("submit", (event) => {
            event.preventDefault();
            submitAnswer(input.value);
          });
          item.append(form);
        }
        item.append(feedback);
          return item;
        }),
    );
  } catch (error) {
    showNotice(getErrorMessage(error), "error");
  }
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
      `Page ${chunk.page_number} | Chunk ${chunk.position + 1} | ${formatNumber(chunk.character_count)} chars`
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
    showNotice("Upload queued for processing.", "success");
    setUploadState("Pending", "status-pending");
    elements.uploadForm.reset();
    elements.selectedFileName.textContent = "Select PDF";
    await refreshDocuments();
    const processedDocument = await waitForDocumentProcessing(documentItem.id);
    setUploadState(
      processedDocument.status === "processed" ? "Processed" : "Failed",
      getStatusClass(processedDocument.status),
    );
    await refreshDocuments();
    await selectDocument(processedDocument.id);
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
        `Page ${result.page_number} | Chunk ${result.chunk_position + 1} | ${formatNumber(result.character_count)} chars`
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
    await requestNoContent(`/documents/${documentId}`, { method: "DELETE" });
    clearSelection();
    await refreshDocuments();
    showNotice("Document deleted.", "success");
  } catch (error) {
    elements.deleteButton.disabled = false;
    showNotice(getErrorMessage(error), "error");
  }
}

elements.uploadForm.addEventListener("submit", handleUpload);
elements.authForm.addEventListener("submit", handleLogin);
elements.registerButton.addEventListener("click", handleRegister);
elements.logoutButton.addEventListener("click", handleLogout);
elements.searchForm.addEventListener("submit", handleSearch);
elements.refreshButton.addEventListener("click", async () => {
  await refreshWorkspace().catch((error) => {
    showNotice(getErrorMessage(error), "error");
  });
});
elements.deleteButton.addEventListener("click", handleDelete);
elements.reviewButton.addEventListener("click", () => {
  if (state.selectedDocumentId !== null) {
    updateProgress(`/documents/${state.selectedDocumentId}/progress/review`, { method: "POST" });
  }
});
elements.masteryButton.addEventListener("click", async () => {
  if (state.selectedDocumentId === null) return;
  const progress = await requestJson(`/documents/${state.selectedDocumentId}/progress`);
  updateProgress(`/documents/${state.selectedDocumentId}/progress`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mastered: !progress.mastered }),
  });
});
elements.summaryButton.addEventListener("click", showSummary);
elements.quizButton.addEventListener("click", showQuiz);
elements.pdfInput.addEventListener("change", () => {
  elements.selectedFileName.textContent =
    elements.pdfInput.files[0]?.name ?? "Select PDF";
});
elements.ownerInput.value = state.ownerId;
elements.ownerInput.addEventListener("change", async () => {
  const ownerId = elements.ownerInput.value.trim();

  if (!ownerId) {
    elements.ownerInput.value = state.ownerId;
    showNotice("Owner must not be empty.", "error");
    return;
  }

  if (!OWNER_ID_PATTERN.test(ownerId)) {
    elements.ownerInput.value = state.ownerId;
    showNotice("Owner contains invalid characters.", "error");
    return;
  }

  state.ownerId = ownerId;
  localStorage.setItem("studygraph.ownerId", ownerId);
  clearSelection();
  elements.searchResults.replaceChildren();
  elements.searchCount.textContent = "0 results";
  await refreshWorkspace().catch((error) => {
    showNotice(getErrorMessage(error), "error");
  });
});

refreshWorkspace().catch((error) => showNotice(getErrorMessage(error), "error"));
updateAuthControls();

setInterval(() => {
  refreshDocuments().catch(() => undefined);
}, 3000);
