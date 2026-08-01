export const VIEWER_RESUME_PREFIX = 'knitting_recipe_viewer_state_v1';

export function createLatestPayloadThrottle(send, intervalMs = 1500, clock = {}) {
  const now = clock.now || Date.now;
  const setTimer = clock.setTimer || setTimeout;
  const clearTimer = clock.clearTimer || clearTimeout;
  let lastSentAt = 0;
  let timer = null;
  let pending = null;

  const dispatch = (keepalive = false) => {
    if (pending == null) return;
    const payload = pending;
    pending = null;
    lastSentAt = now();
    send(payload, { keepalive });
  };

  return {
    queue(payload, { flush = false } = {}) {
      pending = payload;
      if (flush) {
        if (timer != null) clearTimer(timer);
        timer = null;
        dispatch(true);
        return;
      }
      const elapsed = now() - lastSentAt;
      if (elapsed >= intervalMs) {
        dispatch();
      } else if (timer == null) {
        timer = setTimer(() => {
          timer = null;
          dispatch();
        }, intervalMs - elapsed);
      }
    },
    cancel() {
      if (timer != null) clearTimer(timer);
      timer = null;
      pending = null;
    },
  };
}

export function viewerResumeKey(user, recipeId) {
  return `${VIEWER_RESUME_PREFIX}_${user?.id || user?.username || 'guest'}_${recipeId}`;
}

export function readViewerResume(user, recipeId) {
  if (!recipeId || typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(viewerResumeKey(user, recipeId));
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

export function clampIndex(value, max) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(parsed, Math.max(0, max)));
}

export function normalizeViewMode(value) {
  return value === 'charts' ? 'review' : (value || 'original');
}

function requestedViewTakesPrecedence(value) {
  const mode = normalizeViewMode(value);
  return mode === 'review' || mode === 'text';
}

function resolveResumeView(saved, requested) {
  if (requestedViewTakesPrecedence(requested)) return normalizeViewMode(requested);
  return normalizeViewMode(saved?.viewMode || requested);
}

export function normalizeViewerResume(saved, requested = 'original') {
  const sourceMode = saved?.sourceMode === 'pdf' || saved?.sourceMode === 'images'
    ? saved.sourceMode
    : '';
  return {
    viewMode: resolveResumeView(saved, requested),
    sourceMode,
    imageIndex: clampIndex(saved?.imageIndex, 9999),
    zoom: Number.isFinite(Number(saved?.zoom)) ? Math.max(0.5, Math.min(Number(saved.zoom), 4)) : 1,
    scrollY: Number.isFinite(Number(saved?.scrollY)) ? Math.max(0, Number(saved.scrollY)) : null,
    pdfScrollY: Number.isFinite(Number(saved?.pdfScrollY)) ? Math.max(0, Number(saved.pdfScrollY)) : null,
    textScrollY: Number.isFinite(Number(saved?.textScrollY)) ? Math.max(0, Number(saved.textScrollY)) : null,
    mobileImagesVisible: Boolean(saved?.mobileImagesVisible),
    revision: Number.isSafeInteger(Number(saved?.revision)) ? Math.max(0, Number(saved.revision)) : 0,
  };
}

export function resolveViewerResume(localResume, serverResume) {
  const localRevision = Number.isSafeInteger(Number(localResume?.revision))
    ? Math.max(0, Number(localResume.revision))
    : 0;
  const serverRevision = Number.isSafeInteger(Number(serverResume?.revision))
    ? Math.max(0, Number(serverResume.revision))
    : 0;
  if (serverResume?.exists && serverRevision >= localRevision) return serverResume;
  return localResume || serverResume || null;
}

export function resolveRecipeSourceMode(savedMode, recipe) {
  const hasPdf = Boolean(recipe?.has_pdf || recipe?.file_type === 'pdf');
  const hasImages = Boolean(recipe?.has_images || (recipe?.images || []).length > 0);
  if (savedMode === 'pdf' && hasPdf) return 'pdf';
  if (savedMode === 'images' && hasImages) return 'images';
  if (recipe?.preferred_source === 'pdf' && hasPdf) return 'pdf';
  if (recipe?.preferred_source === 'images' && hasImages) return 'images';
  if (hasPdf) return 'pdf';
  return 'images';
}
