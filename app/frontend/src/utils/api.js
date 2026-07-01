const API_BASE = '/api';
function getToken() { return localStorage.getItem('knitting_token') || ''; }
function getCookie(name) {
  return document.cookie
    .split('; ')
    .find(row => row.startsWith(`${name}=`))
    ?.split('=')[1] || '';
}
function authHeaders() {
  const headers = {};
  const legacyToken = getToken();
  if (legacyToken) headers['X-Session-Token'] = legacyToken;
  const csrf = getCookie('knitting_csrf');
  if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf);
  return headers;
}
function fetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const auth = authHeaders();
  for (const [key, value] of Object.entries(auth)) {
    if (!headers[key]) headers[key] = value;
  }
  return window.fetch(url, { ...options, headers, credentials: 'include' });
}

export async function fetchSetupStatus() {
  const res = await fetch(`${API_BASE}/setup/status`);
  if (!res.ok) return { setup_required: false };
  return res.json();
}

export async function createFirstAdmin(username, password) {
  const res = await fetch(`${API_BASE}/setup/admin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Setup failed');
  return data;
}

export async function fetchRecipes({ search='', category='', tags=[], status='', sort='default', page=1, per_page=60 }={}) {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (category) params.set('category', category);
  if (tags.length) params.set('tags', tags.join(','));
  if (status) params.set('status', status);
  if (sort && sort !== 'default') params.set('sort', sort);
  params.set('page', page);
  params.set('per_page', per_page);
  const res = await fetch(`${API_BASE}/recipes?${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load recipes');
  // Returns { recipes, total, page, per_page, pages }
  return res.json();
}
export async function fetchRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Recipe not found');
  return res.json();
}
export async function checkImportDuplicate(recipeId, title) {
  const res = await fetch(`${API_BASE}/import/check-duplicate/${recipeId}?title=${encodeURIComponent(title)}`, { headers: authHeaders() });
  if (!res.ok) return { content_duplicates: [], title_duplicates: [] };
  return res.json();
}
export async function checkDuplicate(files, title) {
  const fd = new FormData();
  fd.append('title', title);
  files.forEach(f => fd.append('files', f));
  const res = await fetch(`${API_BASE}/recipes/check-duplicate`, { method:'POST', headers: authHeaders(), body: fd });
  if (!res.ok) return { content_duplicates: [], title_duplicates: [] };
  return res.json();
}
export async function createRecipe(formData) {
  const res = await fetch(`${API_BASE}/recipes`, { method:'POST', headers: authHeaders(), body: formData });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Upload failed'); }
  return res.json();
}
export async function updateRecipe(id, formData) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, { method:'PUT', headers: authHeaders(), body: formData });
  if (!res.ok) throw new Error('Update failed');
  return res.json();
}
export async function deleteRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, { method:'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('Delete failed');
  return res.json();
}
export async function fetchCategories() {
  const res = await fetch(`${API_BASE}/categories`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}
export async function fetchAllCategories() {
  const res = await fetch(`${API_BASE}/categories?all=true`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}
export async function fetchCategoryDetails() {
  const res = await fetch(`${API_BASE}/categories?all=true&details=true`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}
export async function fetchTags() {
  const res = await fetch(`${API_BASE}/tags`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load tags');
  return res.json();
}
export async function fetchAllTags() {
  const res = await fetch(`${API_BASE}/tags?all=true`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load tags');
  return res.json();
}
export async function fetchTagDetails() {
  const res = await fetch(`${API_BASE}/tags?all=true&details=true`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load tags');
  return res.json();
}
export async function addCategory(name) {
  const res = await fetch(`${API_BASE}/categories`, { method:'POST', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({name}) });
  if (!res.ok) throw new Error('Failed to add category');
  return res.json();
}

export async function deleteCategory(name) {
  const res = await fetch(`${API_BASE}/categories/${encodeURIComponent(name)}`, { method:'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to delete category');
  return res.json();
}
export async function addTag(name) {
  const res = await fetch(`${API_BASE}/tags`, { method:'POST', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({name}) });
  if (!res.ok) throw new Error('Failed to add tag');
  return res.json();
}

export async function deleteTag(name) {
  const res = await fetch(`${API_BASE}/tags/${encodeURIComponent(name)}`, { method:'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to delete tag');
  return res.json();
}
export async function fetchUsers() {
  const res = await fetch(`${API_BASE}/admin/users`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load users');
  return res.json();
}

export async function fetchNavigationProgress() {
  const res = await fetch(`${API_BASE}/auth/navigation-progress`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load navigation progress');
  return res.json();
}

export async function saveNavigationProgress(progress) {
  const res = await fetch(`${API_BASE}/auth/navigation-progress`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(progress),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to save navigation progress');
  return data;
}
export async function createUser(data) {
  const res = await fetch(`${API_BASE}/admin/users`, { method:'POST', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify(data) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Failed to create user'); }
  return res.json();
}
export async function deleteUser(id) {
  const res = await fetch(`${API_BASE}/admin/users/${id}`, { method:'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to delete user');
  return res.json();
}
export async function adminResetPassword(userId, newPassword) {
  const res = await fetch(`${API_BASE}/admin/users/${userId}/reset-password`, { method:'PUT', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({new_password:newPassword}) });
  if (!res.ok) throw new Error('Failed to reset password');
  return res.json();
}
export async function updateUserEmail(userId, email) {
  const res = await fetch(`${API_BASE}/admin/users/${userId}/email`, { method:'PUT', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({ email }) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Failed to update email'); }
  return res.json();
}
export async function sendWelcomeMail(userId, password) {
  const res = await fetch(`${API_BASE}/admin/users/${userId}/welcome-mail`, { method:'POST', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({ password }) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Failed to send welcome email'); }
  return res.json();
}
export async function forgotPassword(usernameOrEmail) {
  const res = await fetch(`${API_BASE}/auth/forgot-password`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username_or_email: usernameOrEmail }) });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}
export async function changePassword(oldPassword, newPassword) {
  const res = await fetch(`${API_BASE}/auth/change-password`, { method:'PUT', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({old_password:oldPassword, new_password:newPassword}) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Failed to change password'); }
  return res.json();
}
// Browser media requests authenticate with the HttpOnly session cookie.
export function thumbnailUrl(recipeId, cacheBust) {
  const base = `${API_BASE}/recipes/${recipeId}/thumbnail`;
  const params = new URLSearchParams();
  if (cacheBust) params.set('v', cacheBust);
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}
export function pdfUrl(recipeId) {
  return `${API_BASE}/recipes/${recipeId}/pdf`;
}
export function imageUrl(recipeId, filename, cacheBust) {
  const base = `${API_BASE}/recipes/${recipeId}/images/${filename}`;
  const params = new URLSearchParams();
  if (cacheBust) params.set('v', cacheBust);
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

export async function rotateImage(recipeId, filename, direction) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/rotate-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ filename, direction }),
  });
  if (!res.ok) throw new Error('Failed to rotate image');
  return res.json();
}

export async function cropImage(recipeId, filename, points) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/images/${encodeURIComponent(filename)}/crop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ points }),
  });
  if (!res.ok) throw new Error('Failed to crop image');
  return res.json();
}

export async function adjustImage(recipeId, filename, adjustments) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/images/${encodeURIComponent(filename)}/adjust`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(adjustments),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to adjust image');
  return data;
}

export async function restoreOriginalImage(recipeId, filename) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/images/${encodeURIComponent(filename)}/restore-original`, {
    method: 'POST',
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to restore image');
  return data;
}

export async function deleteRecipeImage(recipeId, filename) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/images/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to delete image');
  return res.json();
}

export async function fetchTextVersion(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/text-version`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load text version');
  return res.json();
}

export async function fetchViewerProgress(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/viewer-progress`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load viewer progress');
  return res.json();
}

export async function saveViewerProgress(recipeId, progress) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/viewer-progress`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(progress),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to save viewer progress');
  return data;
}

export async function saveTextVersion(recipeId, contentMarkdown, language) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/text-version`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ content_markdown: contentMarkdown, language }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to save text version');
  return data;
}

export async function generateTextVersion(recipeId, language) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/text-version/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ language }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to generate text version');
  return data;
}

export async function createTextVersionJob(recipeId, language) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/text-version/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ language }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to queue text generation');
  return data;
}

export async function fetchReviewSession(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/review-session`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load review session');
  return res.json();
}

export async function saveReviewPage(sessionId, pageId, reviewedText, status = 'draft') {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/pages/${pageId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ reviewed_text: reviewedText, status }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to save review page');
  return data;
}

export async function pauseReviewSession(sessionId) {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/pause`, { method: 'POST', headers: authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to pause review');
  return data;
}

export async function cancelReviewSession(sessionId) {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/cancel`, { method: 'POST', headers: authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to cancel review');
  return data;
}

export async function completeReviewSession(sessionId) {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/complete`, { method: 'POST', headers: authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to complete review');
  return data;
}

export async function createReviewDiagram(sessionId, pageId, payload) {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/pages/${pageId}/diagrams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to create diagram');
  return data;
}

export async function createReviewLegend(sessionId, pageId, payload) {
  const res = await fetch(`${API_BASE}/review-sessions/${sessionId}/pages/${pageId}/legends`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to create legend');
  return data;
}

export function reviewAssetUrl(recipeId, assetPath) {
  return `${API_BASE}/recipes/${recipeId}/review-assets/${assetPath}`;
}

export async function fetchWorkQueue() {
  const res = await fetch(`${API_BASE}/work-queue`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load work queue');
  return res.json();
}

export async function cancelAIJob(jobId) {
  const res = await fetch(`${API_BASE}/work-queue/ai/${jobId}/cancel`, {
    method: 'POST',
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to cancel AI job');
  return data;
}

export async function dismissAIJob(jobId) {
  const res = await fetch(`${API_BASE}/work-queue/ai/${jobId}/dismiss`, {
    method: 'POST',
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to dismiss AI job');
  return data;
}

// Export — fetches the ZIP and triggers a browser download
export async function exportLibrary() {
  const token = getToken();
  const response = await fetch(`${API_BASE}/export`, {
    headers: token ? { "X-Session-Token": token } : {}
  });
  if (!response.ok) throw new Error("Export failed");

  // Get filename from Content-Disposition header if available
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "knitting-library-export.zip";

  // Stream the blob and trigger download
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Annotations
export async function fetchAnnotations(recipeId, pageKey) {
  const res = await fetch(
    `${API_BASE}/recipes/${recipeId}/annotations/${encodeURIComponent(pageKey)}`,
    { headers: authHeaders() }
  );
  if (!res.ok) return [];
  const data = await res.json();
  return data.strokes || [];
}

export async function saveAnnotations(recipeId, pageKey, strokes) {
  const res = await fetch(
    `${API_BASE}/recipes/${recipeId}/annotations/${encodeURIComponent(pageKey)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ strokes }),
    }
  );
  if (!res.ok) throw new Error('Failed to save annotations');
  return res.json();
}

export async function clearAnnotations(recipeId, pageKey) {
  const res = await fetch(
    `${API_BASE}/recipes/${recipeId}/annotations/${encodeURIComponent(pageKey)}`,
    { method: 'DELETE', headers: authHeaders() }
  );
  if (!res.ok) throw new Error('Failed to clear annotations');
  return res.json();
}

// Set custom thumbnail
export async function setThumbnail(recipeId, source, filename) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/set-thumbnail`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ source, filename }),
  });
  if (!res.ok) throw new Error('Failed to set thumbnail');
  return res.json();
}

// Download original recipe (PDF as attachment, images as ZIP)
export function downloadUrl(recipeId) {
  return `${API_BASE}/recipes/${recipeId}/download`;
}

// PDF page images
export async function fetchPdfPages(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/pdf-pages`, { headers: authHeaders() });
  if (!res.ok) return { pages: [] };
  return res.json();
}
export async function convertPdf(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/convert-pdf`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Conversion failed');
  return res.json();
}
export function pdfPageUrl(recipeId, filename) {
  return `${API_BASE}/recipes/${recipeId}/pdf-pages/${filename}`;
}

// Project sessions
export async function startProject(recipeId, yarnId = null, yarnColourId = null, inventoryItemId = null, skeinsUsed = 0) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/start`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      yarn_id: yarnId,
      yarn_colour_id: yarnColourId,
      inventory_item_id: inventoryItemId,
      skeins_used: skeinsUsed,
    }),
  });
  if (!res.ok) throw new Error('Failed to start project');
  return res.json();
}
export async function finishProject(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/finish`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to finish project');
  return res.json();
}

export async function clearSessions(recipeId) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/sessions`, {
    method: 'DELETE', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to clear sessions');
  return res.json();
}

// ── Yarn API ──────────────────────────────────────────────────────────────────
export async function fetchYarns({ search = '', field = '', filterColour = '', filterWoolType = '', filterSeller = '' } = {}) {
  const params = new URLSearchParams();
  if (search)         params.set('search', search);
  if (field)          params.set('field', field);
  if (filterColour)   params.set('filter_colour', filterColour);
  if (filterWoolType) params.set('filter_wool_type', filterWoolType);
  if (filterSeller)   params.set('filter_seller', filterSeller);
  const res = await fetch(`${API_BASE}/yarns?${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load yarns');
  return res.json();
}

export async function fetchYarnAutocomplete(field) {
  const res = await fetch(`${API_BASE}/yarns/autocomplete?field=${field}`, { headers: authHeaders() });
  if (!res.ok) return [];
  const data = await res.json();
  return data.values || [];
}

export async function fetchYarn(id) {
  const res = await fetch(`${API_BASE}/yarns/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Yarn not found');
  return res.json();
}

export async function createYarn(formData) {
  const res = await fetch(`${API_BASE}/yarns`, {
    method: 'POST',
    headers: { 'X-Session-Token': getToken() || '' },
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to create yarn');
  return res.json();
}

export async function updateYarn(id, formData) {
  const res = await fetch(`${API_BASE}/yarns/${id}`, {
    method: 'PUT',
    headers: { 'X-Session-Token': getToken() || '' },
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to update yarn');
  return res.json();
}

export async function deleteYarn(id) {
  const res = await fetch(`${API_BASE}/yarns/${id}`, {
    method: 'DELETE', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to delete yarn');
  return res.json();
}

export function yarnImageUrl(yarnId) {
  return `${API_BASE}/yarns/${yarnId}/image`;
}

export function yarnColourImageUrl(yarnId, colourId) {
  return `${API_BASE}/yarns/${yarnId}/colours/${colourId}/image`;
}

export async function addYarnColour(yarnId, formData) {
  const res = await fetch(`${API_BASE}/yarns/${yarnId}/colours`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to add colour');
  return res.json();
}

export async function deleteYarnColour(yarnId, colourId) {
  const res = await fetch(`${API_BASE}/yarns/${yarnId}/colours/${colourId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to delete colour');
  return res.json();
}

export async function scrapeYarnUrl(url) {
  const res = await fetch(`${API_BASE}/yarns/scrape`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch URL');
  }
  return res.json();
}

// ── Inventory ─────────────────────────────────────────────────────────────────

export async function fetchInventory({ type = '', search = '' } = {}) {
  const params = new URLSearchParams();
  if (type)   params.set('type', type);
  if (search) params.set('search', search);
  const res = await fetch(`${API_BASE}/inventory?${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch inventory');
  return res.json();
}

export async function fetchInventoryItem(id) {
  const res = await fetch(`${API_BASE}/inventory/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch item');
  return res.json();
}

export async function fetchInventoryLog(id) {
  const res = await fetch(`${API_BASE}/inventory/${id}/log`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch log');
  return res.json();
}

export async function createInventoryItem(data) {
  const res = await fetch(`${API_BASE}/inventory`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create item');
  return res.json();
}

export async function updateInventoryItem(id, data) {
  const res = await fetch(`${API_BASE}/inventory/${id}`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update item');
  return res.json();
}

export async function adjustInventory(id, change, reason = 'manual', note = '', recipeId = null, sessionId = null) {
  const res = await fetch(`${API_BASE}/inventory/${id}/adjust`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ change, reason, note, recipe_id: recipeId, session_id: sessionId }),
  });
  if (!res.ok) throw new Error('Failed to adjust inventory');
  return res.json();
}

export async function deleteInventoryItem(id) {
  const res = await fetch(`${API_BASE}/inventory/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to delete item');
  return res.json();
}

// ── Bulk Import ───────────────────────────────────────────────────────────────

// ── Bulk Import API ───────────────────────────────────────────────────────────

/**
 * Upload one group of files (one recipe candidate) to the backend for staging.
 * groupName = the folder name or filename that identifies this recipe.
 * files = array of File objects belonging to this group.
 * Returns { recipe_id, recipe }
 */
export async function uploadImportGroup(groupName, files) {
  const form = new FormData();
  form.append('group_name', groupName);
  for (const file of files) {
    form.append('files', file, file.name);
  }
  const res = await fetch(`${API_BASE}/import/upload-group`, {
    method: 'POST',
    headers: authHeaders(),   // no Content-Type — let browser set multipart boundary
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }
  // Returns { recipe_id, recipe, pdf_pages }
  return res.json();
}

/** Return all currently staged (pending) items so the wizard can resume. */
export async function getImportQueue() {
  const res = await fetch(`${API_BASE}/import/queue`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch import queue');
  return res.json(); // { items: [...], count: N }
}

/** Save metadata onto a staged recipe and mark it done. */
export async function confirmImportItem(recipeId, { title, categories, tags, description }) {
  const res = await fetch(`${API_BASE}/import/confirm/${recipeId}`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, categories, tags, description }),
  });
  if (!res.ok) throw new Error('Failed to confirm import item');
  return res.json();
}

/** Save a custom image order for an image-type recipe. */
export async function saveImageOrder(recipeId, order) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/image-order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ order }),
  });
  if (!res.ok) throw new Error('Failed to save image order');
  return res.json();
}

/** Discard a staged draft recipe — deletes it from the library entirely. */
export async function discardImportItem(recipeId) {
  const res = await fetch(`${API_BASE}/import/discard/${recipeId}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to discard import item');
  return res.json();
}

export async function saveFeedback(recipeId, payload) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/feedback`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to save feedback');
  return res.json();
}

// ── GitHub release notes ─────────────────────────────────────────────────────
export async function listReleases() {
  const res = await fetch(`${API_BASE}/releases`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load releases');
  return res.json();
}
export async function fetchLatestRelease() {
  const res = await fetch(`${API_BASE}/releases/latest`, { headers: authHeaders() });
  if (!res.ok) return { release: null };
  return res.json();
}
export async function fetchPendingReleases() {
  const res = await fetch(`${API_BASE}/releases/pending`, { headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}
export async function dismissRelease(id) {
  const res = await fetch(`${API_BASE}/releases/${id}/dismiss`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to dismiss release');
  return res.json();
}
export async function syncReleases() {
  const res = await fetch(`${API_BASE}/admin/releases/sync`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to sync releases');
  return res.json();
}

// ── Admin: logs ───────────────────────────────────────────────────────────────
export async function fetchLogs(lines = 200, source = 'all') {
  const res = await fetch(`${API_BASE}/admin/logs?lines=${lines}&source=${source}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch logs');
  return res.json();
}

export async function fetchUserActions({ limit = 200, action = '', user = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (action) params.set('action', action);
  if (user) params.set('user', user);
  const res = await fetch(`${API_BASE}/admin/user-actions?${params.toString()}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch user actions');
  return res.json();
}

// ── Admin: mail settings ──────────────────────────────────────────────────────
export async function fetchMailSettings() {
  const res = await fetch(`${API_BASE}/admin/mail`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load mail settings');
  return res.json();
}
export async function saveMailSettings(data) {
  const res = await fetch(`${API_BASE}/admin/mail`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to save mail settings');
  return res.json();
}
export async function testMail(to) {
  const res = await fetch(`${API_BASE}/admin/mail/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ to }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Mail test failed');
  return data;
}
export async function testMailTemplate(to, subject, body) {
  const res = await fetch(`${API_BASE}/admin/mail/templates/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ to, subject, body }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Test failed');
  return data;
}

// ── Admin: AI settings ───────────────────────────────────────────────────────
export async function fetchAISettings() {
  const res = await fetch(`${API_BASE}/admin/ai`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load AI settings');
  return res.json();
}
export async function saveAISettings(data) {
  const res = await fetch(`${API_BASE}/admin/ai`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(result.detail || 'Failed to save AI settings');
  return result;
}
export async function fetchAIModels(data) {
  const res = await fetch(`${API_BASE}/admin/ai/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(result.detail || 'Failed to fetch AI models');
  return result;
}
export async function testAISettings(data) {
  const res = await fetch(`${API_BASE}/admin/ai/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(result.detail || 'AI test failed');
  return result;
}

// ── Admin: 2FA management ─────────────────────────────────────────────────────
export async function fetch2FAStatus() {
  const res = await fetch(`${API_BASE}/admin/2fa/status`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load 2FA status');
  return res.json();
}
export async function adminReset2FA(userId) {
  const res = await fetch(`${API_BASE}/admin/2fa/${userId}`, { method: 'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to reset 2FA');
  return res.json();
}

// ── User: 2FA self-service ────────────────────────────────────────────────────
export async function setup2FA() {
  const res = await fetch(`${API_BASE}/auth/2fa/setup`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to start 2FA setup');
  return res.json();
}
export async function verify2FASetup(code) {
  const res = await fetch(`${API_BASE}/auth/2fa/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ code }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Verification failed');
  return data;
}
export async function disable2FA(password) {
  const res = await fetch(`${API_BASE}/auth/2fa/disable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to disable 2FA');
  return data;
}
export async function verify2FAChallenge(challengeToken, code) {
  const res = await fetch(`${API_BASE}/auth/2fa/challenge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge_token: challengeToken, code }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Invalid code');
  return data;
}

// ── Statistics ───────────────────────────────────────────────────────
export async function fetchStats(aiRange = 'all') {
  const params = new URLSearchParams();
  if (aiRange) params.set('ai_range', aiRange);
  const query = params.toString();
  const res = await fetch(`${API_BASE}/stats${query ? `?${query}` : ''}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load stats');
  return res.json();
}

export async function resetAIStats(range = 'all') {
  const res = await fetch(`${API_BASE}/stats/ai/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ range }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to reset AI stats');
  return data;
}

// ── Bulk recipe actions ───────────────────────────────────────────────
export async function bulkUpdateRecipes(ids, { tags = [], categories = [] } = {}) {
  const res = await fetch(`${API_BASE}/recipes/bulk-update`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ ids, tags, categories }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Bulk update failed');
  return data;
}

// ── Add images to existing recipe ────────────────────────────────────
export async function addImagesToRecipe(recipeId, files) {
  const fd = new FormData();
  for (const file of files) fd.append('files', file);
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/add-images`, {
    method: 'POST',
    headers: authHeaders(),
    body: fd,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to add images');
  return data;
}
