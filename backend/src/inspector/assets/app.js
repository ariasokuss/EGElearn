const INSPECTOR_ROOT = (() => {
  const marker = "/inspector";
  const pathname = window.location.pathname;
  const index = pathname.indexOf(marker);
  return index >= 0 ? pathname.slice(0, index + marker.length) : "/api/v1/inspector";
})();

const API_ROOT = INSPECTOR_ROOT.replace(/\/inspector$/, "");
const FILES_API_ROOT = API_ROOT + "/files";
const storageKeys = {
  userId: "nova_inspector_user_id",
  email: "nova_inspector_email",
  accessToken: "nova_inspector_access_token",
};

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "login") {
    void initLoginPage();
    return;
  }
  if (page === "dashboard") {
    void initDashboardPage();
    return;
  }
  if (page === "folder") {
    void initFolderPage();
    return;
  }
  if (page === "document") {
    void initDocumentPage();
    return;
  }
  if (page === "lessons") {
    void initLessonsPage();
    return;
  }
  if (page === "lesson") {
    void initLessonPage();
  }
});

async function initLoginPage() {
  const flash = document.getElementById("flash");
  const authForm = document.getElementById("authForm");
  const emailInput = document.getElementById("emailInput");
  const passwordInput = document.getElementById("passwordInput");
  const registerButton = document.getElementById("registerButton");
  const manualUserForm = document.getElementById("manualUserForm");
  const manualUserId = document.getElementById("manualUserId");
  const activeSession = document.getElementById("activeSession");
  const continueButton = document.getElementById("continueButton");
  const clearButton = document.getElementById("clearButton");

  const session = loadSession();
  if (session.userId) {
    activeSession.hidden = false;
    activeSession.innerHTML = `
      <strong>${escapeHtml(session.email || "Manual user")}</strong>
      <span class="muted">${escapeHtml(session.userId)}</span>
    `;
    if (continueButton) {
      continueButton.hidden = false;
      continueButton.addEventListener("click", () => {
        window.location.href = `${INSPECTOR_ROOT}/dashboard`;
      });
    }
    if (clearButton) {
      clearButton.hidden = false;
      clearButton.addEventListener("click", () => {
        clearSession();
        window.location.reload();
      });
    }
  }

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runTask(flash, async () => {
      await authenticate({
        flash,
        emailInput,
        passwordInput,
        mode: "login",
      });
    });
  });

  registerButton.addEventListener("click", async () => {
    await runTask(flash, async () => {
      await authenticate({
        flash,
        emailInput,
        passwordInput,
        mode: "register",
      });
    });
  });

  manualUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runTask(flash, async () => {
      const userId = manualUserId.value.trim();
      if (!userId) {
        throw new Error("Paste a user UUID first.");
      }
      saveSession({ userId, email: "Manual user" });
      window.location.href = `${INSPECTOR_ROOT}/dashboard`;
    });
  });
}

async function initDashboardPage() {
  const session = requireSession();
  if (!session) {
    return;
  }

  const flash = document.getElementById("flash");
  bindSessionChrome(session);

  const createFolderForm = document.getElementById("createFolderForm");
  const folderNameInput = document.getElementById("folderNameInput");
  const refreshButton = document.getElementById("refreshButton");
  const summaryMetrics = document.getElementById("summaryMetrics");
  const foldersList = document.getElementById("foldersList");
  const folderEmpty = document.getElementById("folderEmpty");

  createFolderForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runTask(flash, async () => {
      if (!createFolderForm.reportValidity()) {
        return;
      }
      const name = folderNameInput.value.trim();
      await requestJson(`${FILES_API_ROOT}/folders`, {
        method: "POST",
        body: JSON.stringify({ name }),
        headers: authHeaders(session),
      });
      folderNameInput.value = "";
      setFlash(flash, `Folder "${name}" created.`);
      await loadDashboard(session, summaryMetrics, foldersList, folderEmpty);
    });
  });

  refreshButton.addEventListener("click", async () => {
    await runTask(flash, async () => {
      await loadDashboard(session, summaryMetrics, foldersList, folderEmpty);
      setFlash(flash, "Dashboard refreshed.");
    });
  });

  await runTask(flash, async () => {
    await loadDashboard(session, summaryMetrics, foldersList, folderEmpty);
  });
}

async function initFolderPage() {
  const session = requireSession();
  if (!session) {
    return;
  }

  const flash = document.getElementById("flash");
  bindSessionChrome(session);

  const folderId = requiredQueryParam("folder_id");
  if (!folderId) {
    setFlash(flash, "Missing folder_id.", true);
    return;
  }

  const folderTitle = document.getElementById("folderTitle");
  const folderMeta = document.getElementById("folderMeta");
  const folderMetrics = document.getElementById("folderMetrics");
  const documentsList = document.getElementById("documentsList");
  const megaclustersList = document.getElementById("megaclustersList");
  const folderJobs = document.getElementById("folderJobs");
  const uploadForm = document.getElementById("uploadForm");
  const documentFileInput = document.getElementById("documentFileInput");
  const deleteFolderButton = document.getElementById("deleteFolderButton");
  const liveStatus = document.getElementById("liveStatus");

  let folder = null;

  async function refreshFolder(message = "") {
    const overview = await requestJson(
      `${INSPECTOR_ROOT}/overview?user_id=${encodeURIComponent(session.userId)}`,
    );
    folder = overview.folders.find((item) => item.id === folderId) || null;
    if (!folder) {
      throw new Error("Folder not found.");
    }
    renderFolderPage(folderTitle, folderMeta, folderMetrics, documentsList, megaclustersList, folderJobs, folder);
    if (message) {
      setFlash(flash, message);
    }
  }

  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runTask(flash, async () => {
      const files = Array.from(documentFileInput.files || []);
      if (!files.length) {
        throw new Error("Choose one or more PDF or TXT files first.");
      }
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      const response = await requestJson(`${FILES_API_ROOT}/folders/${folderId}/documents/batch`, {
        method: "POST",
        body: formData,
        headers: authHeaders(session),
      });
      documentFileInput.value = "";
      const documents = response.documents || [];
      const queuedJobs = documents
        .map((document) => document.processing_job?.id)
        .filter(Boolean);
      await refreshFolder(
        documents.length === 1
          ? `Upload accepted. Job ${queuedJobs[0] || "queued"} is queued.`
          : `Batch upload accepted. ${documents.length} documents queued.`
      );
    });
  });

  deleteFolderButton.addEventListener("click", async () => {
    await runTask(flash, async () => {
      if (!folder) {
        return;
      }
      if (!window.confirm(`Delete folder "${folder.name}" and all documents?`)) {
        return;
      }
      await requestJson(`${FILES_API_ROOT}/folders/${folder.id}`, {
        method: "DELETE",
        headers: authHeaders(session),
      });
      window.location.href = `${INSPECTOR_ROOT}/dashboard`;
    });
  });

  await runTask(flash, async () => {
    await refreshFolder();
  });

  connectStatusStream({
    url: `${INSPECTOR_ROOT}/folders/${folderId}/stream?user_id=${encodeURIComponent(session.userId)}`,
    eventName: "folder",
    liveStatus,
    onMessage: (payload) => {
      folder = payload;
      renderFolderPage(folderTitle, folderMeta, folderMetrics, documentsList, megaclustersList, folderJobs, folder);
    },
  });
}

async function initDocumentPage() {
  const session = requireSession();
  if (!session) {
    return;
  }

  const flash = document.getElementById("flash");
  bindSessionChrome(session);

  const folderId = requiredQueryParam("folder_id");
  const documentId = requiredQueryParam("document_id");
  if (!folderId || !documentId) {
    setFlash(flash, "Missing folder_id or document_id.", true);
    return;
  }

  const folderBackLink = document.getElementById("folderBackLink");
  const documentTitle = document.getElementById("documentTitle");
  const documentMeta = document.getElementById("documentMeta");
  const storageMetrics = document.getElementById("storageMetrics");
  const storageNotes = document.getElementById("storageNotes");
  const documentJobs = document.getElementById("documentJobs");
  const megaclustersList = document.getElementById("megaclustersList");
  const markdownPreview = document.getElementById("markdownPreview");
  const clustersList = document.getElementById("clustersList");
  const weaviateView = document.getElementById("weaviateView");
  const deleteDocumentButton = document.getElementById("deleteDocumentButton");
  const liveStatus = document.getElementById("liveStatus");

  let detail = null;
  folderBackLink.href = `${INSPECTOR_ROOT}/folder?folder_id=${encodeURIComponent(folderId)}`;

  async function refreshDocument(message = "") {
    detail = await requestJson(
      `${INSPECTOR_ROOT}/folders/${folderId}/documents/${documentId}?user_id=${encodeURIComponent(session.userId)}`,
    );
    renderDocumentPage(
      documentTitle,
      documentMeta,
      storageMetrics,
      storageNotes,
      documentJobs,
      megaclustersList,
      markdownPreview,
      clustersList,
      weaviateView,
      detail,
    );
    folderBackLink.textContent = detail.folder.name;
    if (message) {
      setFlash(flash, message);
    }
  }

  deleteDocumentButton.addEventListener("click", async () => {
    await runTask(flash, async () => {
      if (!detail) {
        return;
      }
      if (!window.confirm(`Delete document "${detail.document.name}"?`)) {
        return;
      }
      await requestJson(`${FILES_API_ROOT}/folders/${folderId}/documents/${documentId}`, {
        method: "DELETE",
        headers: authHeaders(session),
      });
      window.location.href = `${INSPECTOR_ROOT}/folder?folder_id=${encodeURIComponent(folderId)}`;
    });
  });

  await runTask(flash, async () => {
    await refreshDocument();
  });

  connectStatusStream({
    url: `${INSPECTOR_ROOT}/folders/${folderId}/documents/${documentId}/stream?user_id=${encodeURIComponent(session.userId)}`,
    eventName: "document",
    liveStatus,
    onMessage: (payload) => {
      renderDocumentLiveStatus(documentMeta, documentJobs, payload);
    },
  });
}

async function authenticate({ flash, emailInput, passwordInput, mode }) {
  if (!emailInput.form.reportValidity()) {
    return;
  }

  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value;
  if (password.length < 8) {
    throw new Error("Password must be at least 8 characters.");
  }

  if (mode === "register") {
    await requestJson(`${API_ROOT}/auth/register`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  const loginResponse = await requestJson(`${API_ROOT}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  const meResponse = await requestJson(`${API_ROOT}/auth/me`, {
    headers: { Authorization: `Bearer ${loginResponse.access_token}` },
  });

  saveSession({
    userId: meResponse.id,
    email: meResponse.email,
    accessToken: loginResponse.access_token,
  });
  passwordInput.value = "";
  setFlash(flash, `${mode === "register" ? "Registered" : "Logged in"} as ${meResponse.email}.`);
  window.location.href = `${INSPECTOR_ROOT}/dashboard`;
}

async function loadDashboard(session, summaryMetrics, foldersList, folderEmpty) {
  const overview = await requestJson(
    `${INSPECTOR_ROOT}/overview?user_id=${encodeURIComponent(session.userId)}`,
  );
  const totalDocuments = overview.folders.reduce((sum, folder) => sum + folder.document_count, 0);
  const totalClusters = overview.folders.reduce((sum, folder) => sum + folder.cluster_count, 0);
  const totalChunks = overview.folders.reduce((sum, folder) => sum + folder.chunk_count, 0);
  const totalMegaclusters = overview.folders.reduce((sum, folder) => sum + folder.megacluster_count, 0);

  summaryMetrics.innerHTML = [
    metric("Folders", overview.folders.length),
    metric("Documents", totalDocuments),
    metric("Clusters", totalClusters),
    metric("Chunks", totalChunks),
    metric("Megaclusters", totalMegaclusters),
  ].join("");

  if (!overview.folders.length) {
    folderEmpty.hidden = false;
    foldersList.innerHTML = "";
    return;
  }

  folderEmpty.hidden = true;
  foldersList.innerHTML = overview.folders.map(renderFolderCard).join("");
}

function renderFolderPage(
  folderTitle,
  folderMeta,
  folderMetrics,
  documentsList,
  megaclustersList,
  folderJobs,
  folder,
) {
  folderTitle.textContent = folder.name;
  folderMeta.innerHTML = [
    pill(`Created ${formatDate(folder.created_at)}`),
    pill(`Updated ${formatDate(folder.updated_at)}`),
    pill(`${folder.document_count} documents`),
  ].join("");
  folderMetrics.innerHTML = [
    metric("Documents", folder.document_count),
    metric("Clusters", folder.cluster_count),
    metric("Chunks", folder.chunk_count),
    metric("Megaclusters", folder.megacluster_count),
  ].join("");

  documentsList.innerHTML = folder.documents.length
    ? folder.documents.map((document) => renderDocumentCard(folder.id, document)).join("")
    : emptyCard("No documents yet.", "Upload one or more PDF or TXT files to start OCR, clustering, and megaclusters.");

  megaclustersList.innerHTML = folder.megaclusters.length
    ? folder.megaclusters.map(renderMegaclusterCard).join("")
    : emptyCard("No megaclusters yet.", "They will appear when related clusters converge.");

  folderJobs.innerHTML = folder.recent_jobs.length
    ? folder.recent_jobs.map(renderJobCard).join("")
    : emptyCard("No recent jobs.", "Background pipeline activity will appear here.");
}

function renderDocumentPage(
  documentTitle,
  documentMeta,
  storageMetrics,
  storageNotes,
  documentJobs,
  megaclustersList,
  markdownPreview,
  clustersList,
  weaviateView,
  detail,
) {
  documentTitle.textContent = detail.document.name;
  renderDocumentLiveStatus(documentMeta, documentJobs, {
    document: detail.document,
    recent_jobs: detail.recent_jobs,
    cluster_count: detail.storage.database_counts.clusters,
    chunk_count: detail.storage.database_counts.chunks,
  });

  storageMetrics.innerHTML = [
    metric("DB clusters", detail.storage.database_counts.clusters),
    metric("WV clusters", detail.storage.weaviate_counts.clusters),
    metric("DB chunks", detail.storage.database_counts.chunks),
    metric("WV chunks", detail.storage.weaviate_counts.chunks),
    metric("DB megaclusters", detail.storage.database_counts.megaclusters),
    metric("WV megaclusters", detail.storage.weaviate_counts.megaclusters),
  ].join("");

  storageNotes.innerHTML = detail.storage.notes.length
    ? detail.storage.notes.map((note) => `<div class="note-card">${escapeHtml(note)}</div>`).join("")
    : emptyCard("No storage notes.", "");

  megaclustersList.innerHTML = detail.megaclusters.length
    ? detail.megaclusters.map(renderMegaclusterCard).join("")
    : emptyCard("No related megaclusters.", "");

  markdownPreview.textContent = detail.markdown || "Markdown is not available yet.";

  clustersList.innerHTML = detail.clusters.length
    ? detail.clusters.map(renderClusterBundle).join("")
    : emptyCard("No clusters yet.", "The document may still be processing.");

  weaviateView.innerHTML = [
    renderWeaviateSection("Clusters", detail.weaviate.clusters),
    renderWeaviateSection("Chunks", detail.weaviate.chunks),
    renderWeaviateSection("Megaclusters", detail.weaviate.megaclusters),
  ].join("");
}

function renderDocumentLiveStatus(documentMeta, documentJobs, live) {
  documentMeta.innerHTML = [
    statusPill(live.document.processing_status),
    live.document.page_count ? pill(`Pages ${live.document.page_count}`) : "",
    pill(`Created ${formatDate(live.document.created_at)}`),
    pill(`Updated ${formatDate(live.document.updated_at)}`),
    pill(`Clusters ${live.cluster_count}`),
    pill(`Chunks ${live.chunk_count}`),
  ].join("");

  documentJobs.innerHTML = live.recent_jobs.length
    ? live.recent_jobs.map(renderJobCard).join("")
    : emptyCard("No jobs for this document.", "");
}

function syncInspectorToChatSession() {
  const session = loadSession();
  if (session.userId) {
    localStorage.setItem("nc_userId", session.userId);
    localStorage.setItem("nc_base", API_ROOT);
  }
  if (session.accessToken) {
    localStorage.setItem("nc_accessToken", session.accessToken);
  }
  const folderId = requiredQueryParam("folder_id");
  if (folderId) {
    localStorage.setItem("nc_folder", folderId);
  }
}

function bindSessionChrome(session) {
  syncInspectorToChatSession();
  const sessionLabel = document.getElementById("sessionLabel");
  const signOutButton = document.getElementById("signOutButton");
  if (sessionLabel) {
    sessionLabel.textContent = `${session.email || "Manual user"} · ${shortId(session.userId)}`;
  }
  if (signOutButton) {
    signOutButton.addEventListener("click", () => {
      clearSession();
      window.location.href = INSPECTOR_ROOT;
    });
  }
}

function renderFolderCard(folder) {
  return `
    <article class="folder-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Folder</p>
          <h3>${escapeHtml(folder.name)}</h3>
        </div>
        <a class="button accent" href="${INSPECTOR_ROOT}/folder?folder_id=${encodeURIComponent(folder.id)}">Open</a>
      </div>
      <div class="pill-row">
        ${pill(`${folder.document_count} docs`)}
        ${pill(`${folder.cluster_count} clusters`)}
        ${pill(`${folder.chunk_count} chunks`)}
        ${pill(`${folder.megacluster_count} megaclusters`)}
      </div>
      <p class="muted">Updated ${formatDate(folder.updated_at)}</p>
    </article>
  `;
}

function renderDocumentCard(folderId, document) {
  const latestJob = document.recent_jobs[0];
  return `
    <article class="document-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Document</p>
          <h3>${escapeHtml(document.name)}</h3>
        </div>
        <a class="button ghost" href="${INSPECTOR_ROOT}/document?folder_id=${encodeURIComponent(folderId)}&document_id=${encodeURIComponent(document.id)}">Inspect</a>
      </div>
      <div class="pill-row">
        ${statusPill(document.processing_status)}
        ${document.page_count ? pill(`${document.page_count} pages`) : ""}
        ${pill(`${document.cluster_count} clusters`)}
        ${pill(`${document.chunk_count} chunks`)}
      </div>
      <p class="muted">${latestJob ? `${escapeHtml(latestJob.kind)} · ${formatDate(latestJob.updated_at)}` : "No jobs yet."}</p>
    </article>
  `;
}

function renderMegaclusterCard(megacluster) {
  const title = megacluster.name || megacluster.description;
  const description = megacluster.description || title;
  const clusterCount = megacluster.cluster_count ?? (megacluster.cluster_ids || []).length;
  const qdrantClusters = megacluster.qdrant_clusters || [];
  return `
    <article class="megacluster-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Megacluster</p>
          <h3>${escapeHtml(title)}</h3>
          <p class="muted">Description: ${escapeHtml(description)}</p>
        </div>
        ${pill(`${clusterCount} clusters`)}
      </div>
      <div class="pill-row">
        ${pill(`Progress ${megacluster.progress}%`)}
        ${pill(`${(megacluster.document_ids || []).length} documents`)}
      </div>
      ${
        megacluster.cluster_topics.length
          ? `<p class="muted">${escapeHtml(megacluster.cluster_topics.join(" · "))}</p>`
          : `<p class="muted">Created ${formatDate(megacluster.created_at)}</p>`
      }
      ${
        qdrantClusters.length
          ? `
            <details class="detail-card" open>
              <summary>
                <strong>Qdrant clusters</strong>
                ${pill(`${qdrantClusters.length} records`)}
              </summary>
              <div class="detail-body stack">
                ${qdrantClusters.map(renderMegaclusterQdrantCluster).join("")}
              </div>
            </details>
          `
          : ""
      }
    </article>
  `;
}

function renderMegaclusterQdrantCluster(cluster) {
  const properties = cluster.properties || {};
  const title = properties.description || cluster.object_id || "Cluster";
  return `
    <details class="detail-card">
      <summary>
        <div>
          <strong>${escapeHtml(title)}</strong>
          <p class="muted">${escapeHtml(properties.document_id || "Unknown document")}</p>
        </div>
        ${pill(cluster.object_id ? shortId(cluster.object_id) : "cluster")}
      </summary>
      <div class="detail-body">
        <pre class="json-block">${escapeHtml(JSON.stringify(properties, null, 2))}</pre>
      </div>
    </details>
  `;
}

function renderJobCard(job) {
  return `
    <article class="job-card">
      <div class="card-head">
        <div>
          <strong>${escapeHtml(job.kind)}</strong>
          <p class="muted">${formatDate(job.updated_at)}</p>
        </div>
        ${statusPill(job.status)}
      </div>
      <div class="pill-row">
        ${pill(`Attempts ${job.attempts}/${job.max_attempts}`)}
        ${pill(shortId(job.id))}
      </div>
      ${job.error ? `<p class="muted">${escapeHtml(job.error)}</p>` : ""}
    </article>
  `;
}

function renderClusterBundle(bundle) {
  const cluster = bundle.cluster;
  return `
    <details class="detail-card">
      <summary>
        <div>
          <strong>${escapeHtml(cluster.topic_description)}</strong>
          <p class="muted">${escapeHtml(cluster.cluster_type)} · quality ${escapeHtml(String(cluster.content_quality))}/5</p>
        </div>
        <div class="pill-row">
          ${pill(`${bundle.chunks.length} chunks`)}
          ${pill(`Pages ${(cluster.document_pages || []).join(", ") || "n/a"}`)}
        </div>
      </summary>
      <div class="detail-body stack">
        <div class="two-col">
          <div class="note-card">
            <strong>Cluster text</strong>
            <p class="muted">${escapeHtml(cluster.content_text || "Empty")}</p>
          </div>
          <div class="note-card">
            <strong>Metadata</strong>
            <p class="muted">${cluster.created_at ? `Created ${formatDate(cluster.created_at)}` : "Created n/a"}</p>
            <p class="muted">Tokens ${cluster.content_token_count != null ? escapeHtml(String(cluster.content_token_count)) : "n/a"}</p>
            <p class="muted">Cluster ID ${escapeHtml(cluster.cluster_id)}</p>
          </div>
        </div>
        <div class="stack">
          ${bundle.chunks.map(renderChunkCard).join("")}
        </div>
      </div>
    </details>
  `;
}

function renderChunkCard(chunk) {
  return `
    <div class="note-card">
      <div class="pill-row">
        ${pill(`Chunk ${chunk.chunk_index ?? (chunk.chunk_id ? shortId(chunk.chunk_id) : "n/a")}`)}
        ${pill(`Page ${chunk.page}`)}
        ${pill(shortId(chunk.chunk_id))}
      </div>
      <p class="muted">${escapeHtml(chunk.text)}</p>
    </div>
  `;
}

function renderWeaviateSection(label, objects) {
  return `
    <article class="weaviate-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">${escapeHtml(label)}</p>
          <h3>${objects.length} object${objects.length === 1 ? "" : "s"}</h3>
        </div>
      </div>
      ${
        objects.length
          ? objects
              .map(
                (object) => `
                  <details class="detail-card">
                    <summary>
                      <strong>${escapeHtml(object.object_id || "Object")}</strong>
                      ${pill(`${Object.keys(object.properties || {}).length} properties`)}
                    </summary>
                    <div class="detail-body">
                      <pre class="json-block">${escapeHtml(JSON.stringify(object.properties, null, 2))}</pre>
                    </div>
                  </details>
                `,
              )
              .join("")
          : emptyCard(`No ${label.toLowerCase()} objects found.`, "")
      }
    </article>
  `;
}

function loadSession() {
  return {
    userId: window.localStorage.getItem(storageKeys.userId) || "",
    email: window.localStorage.getItem(storageKeys.email) || "",
    accessToken: window.localStorage.getItem(storageKeys.accessToken) || "",
  };
}

function saveSession({ userId, email, accessToken }) {
  window.localStorage.setItem(storageKeys.userId, userId);
  window.localStorage.setItem(storageKeys.email, email);
  if (accessToken) {
    window.localStorage.setItem(storageKeys.accessToken, accessToken);
  }
}

function clearSession() {
  window.localStorage.removeItem(storageKeys.userId);
  window.localStorage.removeItem(storageKeys.email);
}

function requireSession() {
  const session = loadSession();
  if (session.userId) {
    return session;
  }
  window.location.href = INSPECTOR_ROOT;
  return null;
}

function requiredQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function authHeaders(session) {
  if (!session.accessToken) return {};
  return { Authorization: `Bearer ${session.accessToken}` };
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></div>`;
}

function pill(label) {
  return `<span class="pill">${escapeHtml(label)}</span>`;
}

function statusPill(status) {
  const safeStatus = escapeHtml(status);
  return `<span class="status-pill ${safeStatus.toLowerCase()}">${safeStatus}</span>`;
}

function emptyCard(title, body) {
  return `
    <div class="note-card empty-card">
      <strong>${escapeHtml(title)}</strong>
      ${body ? `<p class="muted">${escapeHtml(body)}</p>` : ""}
    </div>
  `;
}

function shortId(value) {
  if (!value) {
    return "";
  }
  return `${String(value).slice(0, 8)}...`;
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

function setFlash(element, message, isError = false) {
  if (!element) {
    return;
  }
  element.hidden = !message;
  element.classList.toggle("error", isError);
  element.textContent = message || "";
}

async function runTask(flash, task) {
  try {
    await task();
  } catch (error) {
    console.error(error);
    setFlash(flash, error.message || String(error), true);
  }
}

async function requestJson(url, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = normalizeErrorMessage(payload);
    throw new Error(detail);
  }

  return payload;
}

function normalizeErrorMessage(payload) {
  if (typeof payload === "string") {
    return payload;
  }
  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) => item.msg || JSON.stringify(item))
      .join("; ");
  }
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }
  return JSON.stringify(payload);
}

function connectStatusStream({ url, eventName, liveStatus, onMessage }) {
  const source = new EventSource(url);

  const setState = (label, isError = false) => {
    if (!liveStatus) {
      return;
    }
    liveStatus.textContent = label;
    liveStatus.classList.toggle("status-error", isError);
  };

  setState("Connecting…");

  source.addEventListener(eventName, (event) => {
    const payload = JSON.parse(event.data);
    onMessage(payload);
    setState("Live updates on");
  });

  source.addEventListener("error", () => {
    setState("Reconnecting…", true);
  });

  window.addEventListener("beforeunload", () => {
    source.close();
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// =============================================================================
// LESSONS PAGE
// =============================================================================

async function initLessonsPage() {
  const session = requireSession();
  if (!session) return;

  const flash = document.getElementById("flash");
  bindSessionChrome(session);

  const refreshButton = document.getElementById("refreshButton");
  const lessonsList = document.getElementById("lessonsList");
  const lessonsEmpty = document.getElementById("lessonsEmpty");

  async function loadLessons() {
    const lessons = await requestJson(
      `${INSPECTOR_ROOT}/api/lessons?user_id=${encodeURIComponent(session.userId)}`,
    );
    if (!lessons.length) {
      lessonsEmpty.hidden = false;
      lessonsList.innerHTML = "";
      return;
    }
    lessonsEmpty.hidden = true;
    lessonsList.innerHTML = lessons.map(renderLessonCard).join("");
  }

  refreshButton.addEventListener("click", async () => {
    await runTask(flash, async () => {
      await loadLessons();
      setFlash(flash, "Lessons refreshed.");
    });
  });

  // ── Upload form ────────────────────────────────────────────────────────
  const uploadLessonForm = document.getElementById("uploadLessonForm");
  const lessonFileInput = document.getElementById("lessonFileInput");
  const lessonNameInput = document.getElementById("lessonNameInput");
  const uploadLessonButton = document.getElementById("uploadLessonButton");
  const uploadResult = document.getElementById("uploadResult");
  const uploadResultContent = document.getElementById("uploadResultContent");

  uploadLessonForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runTask(flash, async () => {
      const file = lessonFileInput.files[0];
      if (!file) throw new Error("Select a .md file first.");

      uploadLessonButton.disabled = true;
      uploadLessonButton.textContent = "Uploading…";
      uploadResult.hidden = true;

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("user_id", session.userId);
        const name = lessonNameInput.value.trim();
        if (name) formData.append("name", name);

        const result = await requestJson(
          `${INSPECTOR_ROOT}/api/lessons/upload`,
          { method: "POST", body: formData },
        );

        uploadResultContent.innerHTML = `
          <div class="pill-row">
            ${pill(escapeHtml(result.lesson.name || "Untitled"))}
            ${pill(`${result.num_blocks} block${result.num_blocks === 1 ? "" : "s"} parsed`)}
          </div>
          <a class="button accent" style="margin-top:0.4rem;width:fit-content"
             href="${INSPECTOR_ROOT}/lessons/${encodeURIComponent(result.lesson.id)}?lesson_id=${encodeURIComponent(result.lesson.id)}">
            Open lesson →
          </a>
        `;
        uploadResult.hidden = false;

        uploadLessonForm.reset();
        await loadLessons();
        setFlash(flash, `"${result.lesson.name}" uploaded — ${result.num_blocks} blocks created.`);
      } finally {
        uploadLessonButton.disabled = false;
        uploadLessonButton.textContent = "Upload & Parse";
      }
    });
  });

  await runTask(flash, async () => {
    await loadLessons();
  });
}

// =============================================================================
// LESSON DETAIL PAGE
// =============================================================================

async function initLessonPage() {
  const session = requireSession();
  if (!session) return;

  const flash = document.getElementById("flash");
  bindSessionChrome(session);

  const lessonId = requiredQueryParam("lesson_id");
  if (!lessonId) {
    setFlash(flash, "Missing lesson_id.", true);
    return;
  }

  const lessonTitle = document.getElementById("lessonTitle");
  const lessonMeta = document.getElementById("lessonMeta");
  const lessonBlocksList = document.getElementById("lessonBlocksList");

  async function loadLesson(message = "") {
    let detail = await requestJson(
      `${INSPECTOR_ROOT}/api/lessons/${encodeURIComponent(lessonId)}?user_id=${encodeURIComponent(session.userId)}`,
    );

    // Auto-parse feynman blocks on first load if none exist yet
    if (detail.feynman_blocks.length === 0 && detail.blocks.length > 0) {
      try {
        await requestJson(
          `${INSPECTOR_ROOT}/api/lessons/${encodeURIComponent(lessonId)}/parse-feynman?user_id=${encodeURIComponent(session.userId)}`,
          { method: "POST", headers: {} },
        );
        detail = await requestJson(
          `${INSPECTOR_ROOT}/api/lessons/${encodeURIComponent(lessonId)}?user_id=${encodeURIComponent(session.userId)}`,
        );
      } catch {
        // Non-fatal — feynman directives will render as stubs
      }
    }

    lessonTitle.textContent = detail.lesson.name || "Untitled Lesson";
    lessonMeta.innerHTML = [
      pill(`${detail.blocks.length} block${detail.blocks.length === 1 ? "" : "s"}`),
      pill(`${detail.feynman_blocks.length} feynman`),
      pill(`Created ${formatDate(detail.lesson.created_at)}`),
    ].join("");

    lessonBlocksList.innerHTML = detail.blocks.length
      ? detail.blocks.map((b) => renderLessonBlockContent(b, detail.feynman_blocks)).join("")
      : emptyCard("No lesson blocks found.", "");

    attachFeynmanWidgets(lessonBlocksList, session);

    if (message) setFlash(flash, message);
  }

  await runTask(flash, async () => {
    await loadLesson();
  });
}

// =============================================================================
// LESSON RENDER HELPERS
// =============================================================================

function renderLessonCard(lesson) {
  return `
    <article class="folder-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Lesson</p>
          <h3>${escapeHtml(lesson.name || "Untitled")}</h3>
        </div>
        <a class="button accent" href="${INSPECTOR_ROOT}/lessons/${encodeURIComponent(lesson.id)}?lesson_id=${encodeURIComponent(lesson.id)}">Open</a>
      </div>
      <div class="pill-row">
        ${lesson.num_blocks != null ? pill(`${lesson.num_blocks} blocks`) : ""}
        ${pill(`Created ${formatDate(lesson.created_at)}`)}
      </div>
    </article>
  `;
}


function renderLessonBlockContent(block, feynmanBlocks) {
  const storedFeynmanIds = new Set((feynmanBlocks || []).map((fb) => fb.id));
  const content = block.content || "";
  const rendered = renderCustomBlocks(content, block.block_number, feynmanBlocks || []);
  return `
    <div class="lesson-block">
      <span class="block-number-pill">#${block.block_number}</span>
      ${block.is_summary ? `<span class="status-pill">Summary</span>` : ""}
      <div class="lesson-content">${rendered}</div>
    </div>
  `;
}

/**
 * Render lesson markdown with awareness of custom ::: directives.
 * Falls back to marked.js for plain markdown segments.
 */
function renderCustomBlocks(content, blockNumber, feynmanBlocks) {
  // Split on custom directive boundaries
  const parts = splitOnDirectives(content);
  return parts.map((part) => {
    if (part.type === "text") {
      return typeof marked !== "undefined"
        ? marked.parse(part.content)
        : `<p>${escapeHtml(part.content)}</p>`;
    }
    return renderDirective(part, blockNumber, feynmanBlocks);
  }).join("");
}

function splitOnDirectives(content) {
  const parts = [];
  const directiveRe = /^:::\s*(\w+)[^\n]*\n([\s\S]*?)^:::\s*$/gm;
  let lastIndex = 0;
  let match;

  while ((match = directiveRe.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: content.slice(lastIndex, match.index) });
    }
    parts.push({ type: "directive", name: match[1].toLowerCase(), body: match[2], raw: match[0] });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: "text", content: content.slice(lastIndex) });
  }
  return parts;
}

function renderDirective(part, blockNumber, feynmanBlocks) {
  const { name, body } = part;

  if (name === "definition") {
    const titleMatch = part.raw.match(/^:::\s*definition\s*\[([^\]]*)\]/);
    const title = titleMatch ? titleMatch[1] : "Definition";
    return `
      <div class="block-definition">
        <p class="block-label">📖 ${escapeHtml(title)}</p>
        <div>${typeof marked !== "undefined" ? marked.parse(body) : escapeHtml(body)}</div>
      </div>
    `;
  }

  if (name === "question") {
    const typeMatch = part.raw.match(/^:::\s*question\s+(\w+)/);
    const qType = typeMatch ? typeMatch[1].toUpperCase() : "QUESTION";
    return `
      <div class="block-question">
        <p class="block-label">❓ ${escapeHtml(qType)}</p>
        <div>${typeof marked !== "undefined" ? marked.parse(body) : escapeHtml(body)}</div>
      </div>
    `;
  }

  if (name === "application") {
    return `
      <div class="block-application">
        <p class="block-label">🌍 Application</p>
        <div>${typeof marked !== "undefined" ? marked.parse(body) : escapeHtml(body)}</div>
      </div>
    `;
  }

  if (name === "feynman") {
    return renderFeynmanDirective(body, blockNumber, feynmanBlocks);
  }

  // Unknown directive — render as plain text
  return typeof marked !== "undefined" ? marked.parse(body) : escapeHtml(body);
}

function renderFeynmanDirective(body, blockNumber, feynmanBlocks) {
  // Parse scope
  const scopeMatch = body.match(/^\s*scope\s*:\s*(.+)$/m);
  const scopeNums = scopeMatch
    ? scopeMatch[1].split(",").map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite)
    : [];
  const scopeLabel = scopeNums.length ? `Blocks ${scopeNums.join(", ")}` : "All blocks";

  // Parse question and points
  const lines = body.split("\n").filter((l) => !l.match(/^\s*scope\s*:/));
  const pointsIdx = lines.findIndex((l) => l.match(/^\s*points\s*:\s*$/));
  const questionLines = pointsIdx >= 0 ? lines.slice(0, pointsIdx) : lines;
  const pointLines = pointsIdx >= 0 ? lines.slice(pointsIdx + 1) : [];
  const question = questionLines.join("\n").trim();
  const points = pointLines.map((l) => l.replace(/^\s*-\s*/, "").trim()).filter(Boolean);

  // Match against DB-stored feynman blocks
  const stored = feynmanBlocks.find((fb) => {
    const fbScopes = fb.scope || [];
    return fbScopes.length === scopeNums.length &&
      scopeNums.every((n) => fbScopes.includes(n)) &&
      fb.question.slice(0, 60) === question.slice(0, 60);
  });

  if (!stored) {
    // Fallback — not in DB yet (shouldn't happen after auto-parse)
    return `
      <div class="block-feynman">
        <p class="block-label">🧠 Feynman — ${escapeHtml(scopeLabel)} <span class="missing-badge">Not parsed</span></p>
        <p class="feynman-question">${escapeHtml(question)}</p>
      </div>`;
  }

  const pointsPreviewHtml = points.map((p) =>
    `<li>${escapeHtml(p)}</li>`
  ).join("");

  const pointsTrackHtml = points.map((p, i) =>
    `<div class="fw-point-item" data-index="${i}">
      <span class="fw-point-icon">○</span>
      <span>${escapeHtml(p)}</span>
    </div>`
  ).join("");

  return `
    <div class="block-feynman feynman-widget" data-feynman-block-id="${escapeHtml(stored.id)}">
      <!-- IDLE -->
      <div class="fw-idle">
        <p class="block-label">🧠 Feynman — ${escapeHtml(scopeLabel)}</p>
        <p class="feynman-question">${escapeHtml(question)}</p>
        ${points.length ? `<ul class="feynman-points">${pointsPreviewHtml}</ul>` : ""}
        <div class="feynman-actions">
          <button class="button accent fw-start-btn">Start exercise</button>
        </div>
      </div>
      <!-- CHAT (shown after Start) -->
      <div class="fw-chat" hidden>
        <div class="fw-progress-row">
          <div class="fw-iter-track">
            <div class="fw-iter-dot fw-active"></div>
            <div class="fw-iter-dot"></div>
            <div class="fw-iter-dot"></div>
          </div>
          <span class="fw-iter-label">Question 1 of 3</span>
        </div>
        <div class="fw-points-track">${pointsTrackHtml}</div>
        <div class="fw-messages"></div>
        <div class="fw-summary" hidden></div>
        <div class="fw-input-bar">
          <textarea class="fw-textarea" placeholder="Type your answer… (Enter to send, Shift+Enter for new line)" rows="3" disabled></textarea>
          <button class="button accent fw-send-btn" disabled>Send</button>
        </div>
      </div>
    </div>`;
}

// =============================================================================
// FEYNMAN INLINE WIDGET
// =============================================================================

function attachFeynmanWidgets(container, session) {
  container.querySelectorAll(".feynman-widget[data-feynman-block-id]").forEach((widget) => {
    widget._fw = null;
    const blockId = widget.dataset.feynmanBlockId;
    const startBtn = widget.querySelector(".fw-start-btn");
    if (!startBtn) return;

    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      startBtn.textContent = "Starting…";
      try {
        await fwStartSession(widget, blockId, session);
      } catch (err) {
        startBtn.disabled = false;
        startBtn.textContent = "Start exercise";
        let errEl = widget.querySelector(".fw-start-error");
        if (!errEl) {
          errEl = document.createElement("p");
          errEl.className = "fw-start-error";
          errEl.style.cssText = "color:var(--danger);font-size:0.88rem;margin-top:0.4rem;";
          widget.querySelector(".fw-idle").appendChild(errEl);
        }
        errEl.textContent = err.message || "Failed to start";
      }
    });
  });
}

async function fwStartSession(widget, blockId, session) {
  const resp = await requestJson(`${API_ROOT}/feynman/session`, {
    method: "POST",
    headers: authHeaders(session),
    body: JSON.stringify({ feynman_block_id: blockId }),
  });

  widget._fw = {
    sessionId: resp.session.id,
    block: resp.feynman_block,
    iteration: resp.session.current_iteration,
    completed: false,
  };

  widget.querySelector(".fw-idle").hidden = true;
  widget.querySelector(".fw-chat").hidden = false;

  fwUpdateProgress(widget, 1, false);
  fwUpdatePoints(widget, null);
  fwAppendMessage(widget, "assistant", resp.first_message.content);
  fwEnableInput(widget);

  const sendBtn = widget.querySelector(".fw-send-btn");
  const textarea = widget.querySelector(".fw-textarea");
  sendBtn.addEventListener("click", () => fwSendAnswer(widget, session));
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); fwSendAnswer(widget, session); }
  });
}

async function fwSendAnswer(widget, session) {
  if (!widget._fw || widget._fw.completed) return;
  const textarea = widget.querySelector(".fw-textarea");
  const answer = textarea.value.trim();
  if (!answer) return;

  fwAppendMessage(widget, "user", answer);
  textarea.value = "";
  fwDisableInput(widget);
  fwShowThinking(widget);

  try {
    await fwStreamAnswer(widget, answer, session);
  } catch (err) {
    fwRemoveThinking(widget);
    fwAppendMessage(widget, "assistant", "⚠ " + (err.message || "Error"));
    fwEnableInput(widget);
  }
}

async function fwStreamAnswer(widget, answer, session) {
  const { sessionId } = widget._fw;

  const resp = await fetch(
    `${API_ROOT}/feynman/session/${encodeURIComponent(sessionId)}/answer`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(session) },
      body: JSON.stringify({ answer }),
    },
  );

  if (!resp.ok) {
    const b = await resp.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamingBubble = null;
  let streamingText = "";

  fwRemoveThinking(widget);

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (const part of parts) {
      if (!part.trim()) continue;
      let eventName = "", dataStr = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice(7).trim();
        if (line.startsWith("data: ")) dataStr = line.slice(6);
      }
      if (!eventName || !dataStr) continue;
      let payload;
      try { payload = JSON.parse(dataStr); } catch { continue; }

      if (eventName === "token") {
        if (!streamingBubble) streamingBubble = fwAppendMessage(widget, "assistant", "");
        streamingText += payload.content;
        streamingBubble.querySelector(".fw-msg-bubble").textContent = streamingText;
        fwScrollToBottom(widget);
      } else if (eventName === "message_complete") {
        streamingBubble = null; streamingText = "";
        widget._fw.iteration = payload.iteration;
        fwUpdateProgress(widget, payload.iteration, false);
        fwUpdatePoints(widget, payload.covered || null);
        fwEnableInput(widget);
      } else if (eventName === "summary") {
        widget._fw.completed = true;
        fwUpdateProgress(widget, 3, true);
        fwUpdatePoints(widget, payload.covered);
        fwShowSummary(widget, payload);
        widget.querySelector(".fw-input-bar").hidden = true;
      } else if (eventName === "error") {
        fwAppendMessage(widget, "assistant", "⚠ " + (payload.detail || "Unknown error"));
        fwEnableInput(widget);
      }
    }
  }
}

function fwAppendMessage(widget, role, content) {
  const messages = widget.querySelector(".fw-messages");
  const div = document.createElement("div");
  div.className = `fw-msg fw-msg--${role}`;
  div.innerHTML = `
    <span class="fw-msg-label">${role === "assistant" ? "Nova" : "You"}</span>
    <div class="fw-msg-bubble">${escapeHtml(content)}</div>`;
  messages.appendChild(div);
  fwScrollToBottom(widget);
  return div;
}

function fwShowThinking(widget) {
  const messages = widget.querySelector(".fw-messages");
  const div = document.createElement("div");
  div.className = "fw-msg fw-msg--assistant fw-thinking-msg";
  div.innerHTML = `
    <span class="fw-msg-label">Nova</span>
    <div class="fw-msg-bubble"><div class="fw-thinking"><span></span><span></span><span></span></div></div>`;
  messages.appendChild(div);
  fwScrollToBottom(widget);
}

function fwRemoveThinking(widget) {
  const el = widget.querySelector(".fw-thinking-msg");
  if (el) el.remove();
}

function fwUpdateProgress(widget, iteration, done) {
  widget.querySelectorAll(".fw-iter-dot").forEach((dot, i) => {
    dot.className = "fw-iter-dot";
    const n = i + 1;
    if (done || n < iteration) dot.classList.add("fw-done");
    else if (n === iteration) dot.classList.add("fw-active");
  });
  const label = widget.querySelector(".fw-iter-label");
  if (label) label.textContent = done ? "Complete" : `Question ${iteration} of 3`;
}

function fwUpdatePoints(widget, covered) {
  widget.querySelectorAll(".fw-point-item").forEach((item, i) => {
    const icon = item.querySelector(".fw-point-icon");
    item.classList.remove("fw-covered", "fw-missed");
    if (!covered) { icon.textContent = "○"; return; }
    if (covered[i]) { icon.textContent = "✓"; item.classList.add("fw-covered"); }
    else { icon.textContent = "✗"; item.classList.add("fw-missed"); }
  });
}

function fwShowSummary(widget, payload) {
  const points = (widget._fw.block && widget._fw.block.points) || [];
  const pointsHtml = points.map((p, i) => {
    const ok = payload.covered && payload.covered[i];
    return `<div class="fw-pr-item ${ok ? "fw-covered" : "fw-missed"}">
      <span>${ok ? "✓" : "✗"}</span><span>${escapeHtml(p)}</span>
    </div>`;
  }).join("");

  const summary = widget.querySelector(".fw-summary");
  summary.innerHTML = `
    <div class="fw-summary-card">
      <p class="fw-summary-title">${payload.all_covered ? "🎉 Well done!" : "Session complete"}</p>
      <p class="fw-summary-text">${escapeHtml(payload.text)}</p>
      ${pointsHtml ? `<div class="fw-points-result">${pointsHtml}</div>` : ""}
    </div>`;
  summary.hidden = false;
  fwScrollToBottom(widget);
}

function fwEnableInput(widget) {
  const ta = widget.querySelector(".fw-textarea");
  const btn = widget.querySelector(".fw-send-btn");
  if (ta) { ta.disabled = false; ta.focus(); }
  if (btn) btn.disabled = false;
}

function fwDisableInput(widget) {
  const ta = widget.querySelector(".fw-textarea");
  const btn = widget.querySelector(".fw-send-btn");
  if (ta) ta.disabled = true;
  if (btn) btn.disabled = true;
}

function fwScrollToBottom(widget) {
  const messages = widget.querySelector(".fw-messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}
