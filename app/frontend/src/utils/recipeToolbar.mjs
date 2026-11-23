// Presentation choices map to existing persisted viewer modes.
export function recipeReadingViews(recipe, showText) {
  const views = [];
  if (recipe?.has_pdf || recipe?.file_type === 'pdf') views.push('pdf');
  if (recipe?.has_images || recipe?.images?.length) views.push('images');
  if (!views.length) views.push('original');
  if (showText) views.push('text');
  return views;
}
export function readingViewSelection(view) {
  return view === 'text' ? { viewMode: 'text' }
    : { viewMode: 'original', ...(view !== 'original' ? { sourceMode: view } : {}) };
}
