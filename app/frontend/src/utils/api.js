/**
 * api.js
 * All functions that talk to the backend API live here.
 * This makes it easy to find and change API calls in one place.
 */

const API_BASE = '/api';

/**
 * Fetch all recipes, with optional search/filter parameters.
 * @param {Object} params - { search, category, tags }
 */
export async function fetchRecipes({ search = '', category = '', tags = [] } = {}) {
  const params = new URLSearchParams();
  if (search)   params.set('search', search);
  if (category) params.set('category', category);
  if (tags.length) params.set('tags', tags.join(','));

  const res = await fetch(`${API_BASE}/recipes?${params}`);
  if (!res.ok) throw new Error('Failed to load recipes');
  return res.json();
}

/**
 * Fetch a single recipe by its ID.
 */
export async function fetchRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`);
  if (!res.ok) throw new Error('Recipe not found');
  return res.json();
}

/**
 * Upload a new recipe with files and metadata.
 * @param {FormData} formData - includes files + title/description/categories/tags
 */
export async function createRecipe(formData) {
  const res = await fetch(`${API_BASE}/recipes`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}

/**
 * Update the metadata of an existing recipe.
 */
export async function updateRecipe(id, formData) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, {
    method: 'PUT',
    body: formData,
  });
  if (!res.ok) throw new Error('Update failed');
  return res.json();
}

/**
 * Delete a recipe permanently.
 */
export async function deleteRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Delete failed');
  return res.json();
}

/**
 * Fetch all available categories.
 */
export async function fetchCategories() {
  const res = await fetch(`${API_BASE}/categories`);
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}

/**
 * Fetch all tags used by at least one recipe.
 */
export async function fetchTags() {
  const res = await fetch(`${API_BASE}/tags`);
  if (!res.ok) throw new Error('Failed to load tags');
  return res.json();
}

/**
 * Add a new category.
 */
export async function addCategory(name) {
  const res = await fetch(`${API_BASE}/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Failed to add category');
  return res.json();
}

/**
 * Build the URL for a recipe's thumbnail image.
 */
export function thumbnailUrl(recipeId) {
  return `${API_BASE}/recipes/${recipeId}/thumbnail`;
}

/**
 * Build the URL for a recipe's PDF file.
 */
export function pdfUrl(recipeId) {
  return `${API_BASE}/recipes/${recipeId}/pdf`;
}

/**
 * Build the URL for a specific image in an image recipe.
 */
export function imageUrl(recipeId, filename) {
  return `${API_BASE}/recipes/${recipeId}/images/${filename}`;
}
