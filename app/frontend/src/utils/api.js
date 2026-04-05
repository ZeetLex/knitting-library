const API_BASE = '/api';
function getToken() { return localStorage.getItem('knitting_token') || ''; }
function authHeaders() { return { 'X-Session-Token': getToken() }; }

export async function fetchRecipes({ search='', category='', tags=[], status='', page=1, per_page=60 }={}) {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (category) params.set('category', category);
  if (tags.length) params.set('tags', tags.join(','));
  if (status) params.set('status', status);
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
export async function fetchTags() {
  const res = await fetch(`${API_BASE}/tags`, { headers: authHeaders() });
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
export async function fetchUsers() {
  const res = await fetch(`${API_BASE}/admin/users`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load users');
  return res.json();
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
export async function changePassword(oldPassword, newPassword) {
  const res = await fetch(`${API_BASE}/auth/change-password`, { method:'PUT', headers:{'Content-Type':'application/json',...authHeaders()}, body: JSON.stringify({old_password:oldPassword, new_password:newPassword}) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.detail || 'Failed to change password'); }
  return res.json();
}
// File URLs include the token as a query param so the browser can load them
// directly in <img> and <iframe> tags without needing custom headers.
export function thumbnailUrl(recipeId, cacheBust) {
  const t = getToken();
  const base = `${API_BASE}/recipes/${recipeId}/thumbnail`;
  const params = new URLSearchParams();
  if (t) params.set('token', t);
  if (cacheBust) params.set('v', cacheBust);
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}
export function pdfUrl(recipeId) {
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/pdf${t ? '?token=' + t : ''}`;
}
export function imageUrl(recipeId, filename, cacheBust) {
  const t = getToken();
  const base = `${API_BASE}/recipes/${recipeId}/images/${filename}`;
  const params = new URLSearchParams();
  if (t) params.set('token', t);
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

export async function deleteRecipeImage(recipeId, filename) {
  const res = await fetch(`${API_BASE}/recipes/${recipeId}/images/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to delete image');
  return res.json();
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
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/download${t ? '?token=' + t : ''}`;
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
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/pdf-pages/${filename}${t ? '?token=' + t : ''}`;
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
  const t = getToken();
  return `${API_BASE}/yarns/${yarnId}/image${t ? '?token=' + t : ''}`;
}

export function yarnColourImageUrl(yarnId, colourId) {
  const t = getToken();
  return `${API_BASE}/yarns/${yarnId}/colours/${colourId}/image${t ? '?token=' + t : ''}`;
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

// ── Announcements ─────────────────────────────────────────────────────────────
export async function createAnnouncement(title, body) {
  const res = await fetch(`${API_BASE}/admin/announcements`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ title, body }),
  });
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed to push announcement'); }
  return res.json();
}
export async function listAnnouncements() {
  const res = await fetch(`${API_BASE}/admin/announcements`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load announcements');
  return res.json();
}
export async function fetchPendingAnnouncements() {
  const res = await fetch(`${API_BASE}/announcements/pending`, { headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}
export async function dismissAnnouncement(id) {
  const res = await fetch(`${API_BASE}/announcements/${id}/dismiss`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error('Failed to dismiss');
  return res.json();
}

// ── Admin: logs ───────────────────────────────────────────────────────────────
export async function fetchLogs(lines = 200, source = 'all') {
  const res = await fetch(`${API_BASE}/admin/logs?lines=${lines}&source=${source}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch logs');
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

// ── Statistics ───────────────────────────────────────────────────────────────────
export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load statistics');
  return res.json();
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
