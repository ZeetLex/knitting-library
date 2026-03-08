const API_BASE = '/api';
function getToken() { return localStorage.getItem('knitting_token') || ''; }
function authHeaders() { return { 'X-Session-Token': getToken() }; }

export async function fetchRecipes({ search='', category='', tags=[] }={}) {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (category) params.set('category', category);
  if (tags.length) params.set('tags', tags.join(','));
  const res = await fetch(`${API_BASE}/recipes?${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load recipes');
  return res.json();
}
export async function fetchRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Recipe not found');
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
export function thumbnailUrl(recipeId) {
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/thumbnail${t ? '?token=' + t : ''}`;
}
export function pdfUrl(recipeId) {
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/pdf${t ? '?token=' + t : ''}`;
}
export function imageUrl(recipeId, filename) {
  const t = getToken();
  return `${API_BASE}/recipes/${recipeId}/images/${filename}${t ? '?token=' + t : ''}`;
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
