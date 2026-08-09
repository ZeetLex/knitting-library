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
    fullscreen: Boolean(saved?.fullscreen),
    pdfAnchor: normalizePdfAnchor(saved?.pdfAnchor),
    revision: Number.isSafeInteger(Number(saved?.revision)) ? Math.max(0, Number(saved.revision)) : 0,
  };
}

export function normalizePdfAnchor(anchor) {
  const pageIndex = Number.parseInt(anchor?.pageIndex, 10);
  const offsetRatio = Number(anchor?.offsetRatio);
  if (!Number.isFinite(pageIndex) || pageIndex < 0 || !Number.isFinite(offsetRatio)) return null;
  return {
    pageIndex: Math.min(pageIndex, 9999),
    offsetRatio: Math.max(0, Math.min(offsetRatio, 1)),
  };
}

export function pdfScrollTopForAnchor(anchor, pageTop, pageHeight, viewportHeight, maxScroll) {
  const normalized = normalizePdfAnchor(anchor);
  const top = Number(pageTop);
  const height = Number(pageHeight);
  const viewport = Number(viewportHeight);
  const maximum = Number(maxScroll);
  if (!normalized || !Number.isFinite(top) || !Number.isFinite(height) || height <= 0 ||
      !Number.isFinite(viewport) || !Number.isFinite(maximum)) return null;
  const target = top + (height * normalized.offsetRatio) - (viewport / 2);
  return Math.max(0, Math.min(target, Math.max(0, maximum)));
}

export function mergeLocalViewerPresentation(resolved, localResume) {
  const resolvedRevision = Number(resolved?.revision) || 0;
  const localRevision = Number(localResume?.revision) || 0;
  return {
    ...(resolved || {}),
    fullscreen: Boolean(localResume?.fullscreen),
    pdfAnchor: localRevision >= resolvedRevision ? normalizePdfAnchor(localResume?.pdfAnchor) : null,
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
  // PDF availability always wins on open, even over a previously saved/resumed
  // preference — the PDF view is the better reading experience and should be
  // the default whenever there's a PDF to show.
  if (hasPdf) return 'pdf';
  if (savedMode === 'images' && hasImages) return 'images';
  if (recipe?.preferred_source === 'images' && hasImages) return 'images';
  if (hasImages) return 'images';
  return savedMode || 'images';
}
