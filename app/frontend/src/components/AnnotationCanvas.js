/**
 * AnnotationCanvas.js
 *
 * The image is drawn directly onto the canvas (no separate <img> tag).
 * Annotations are painted on top. Because canvas IS the image, markings
 * scroll with the document perfectly — there's no overlay to drift.
 *
 * The canvas is sized to fill its container width and grow as tall as
 * needed to keep the image's aspect ratio. Zoom is disabled — users
 * pinch-zoom naturally on mobile or use browser zoom.
 */

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Pencil, PenLine as Highlighter, Trash2, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchAnnotations, saveAnnotations, clearAnnotations } from '../utils/api';
import { useApp } from '../utils/AppContext';
import './AnnotationCanvas.css';

const DEFAULTS = {
  pencil:    { size: 3,  opacity: 1.0, color: '#e05555' },
  highlight: { size: 24, opacity: 0.35, color: '#ffe066' },
};
const PRESET_COLORS = [
  '#e05555','#f4a94e','#ffe066','#6dbf6d',
  '#4e9af4','#b46df4','#f47ab0','#1a1a2e',
];

/* ─────────────────────────────────────────────────────────────────────────────
   ImageAnnotationCanvas
   Replaces the <img> tag entirely. Canvas draws the image then annotations.
───────────────────────────────────────────────────────────────────────────── */
export function ImageAnnotationCanvas({ recipeId, pageKey, src }) {
  const { t } = useApp();
  const canvasRef   = useRef(null);
  const imageRef    = useRef(null);
  const drawing     = useRef(false);
  const currentPath = useRef([]);
  const containerRef = useRef(null);

  const [strokes, setStrokes]         = useState([]);
  const [tool, setTool]               = useState('pencil');
  const [color, setColor]             = useState(DEFAULTS.pencil.color);
  const [size, setSize]               = useState(DEFAULTS.pencil.size);
  const [opacity, setOpacity]         = useState(DEFAULTS.pencil.opacity);
  const [toolbarOpen, setToolbarOpen] = useState(false);
  const [ready, setReady]             = useState(false);

  const strokesRef = useRef(strokes);
  useEffect(() => { strokesRef.current = strokes; }, [strokes]);

  // ── Load image ────────────────────────────────────────────────────────────
  useEffect(() => {
    setReady(false);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload  = () => { imageRef.current = img; setReady(true); };
    img.onerror = () => setReady(true);
    img.src = src;
  }, [src]);

  // ── Load annotations ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!recipeId || !pageKey) return;
    fetchAnnotations(recipeId, pageKey).then(setStrokes).catch(() => {});
  }, [recipeId, pageKey]);

  // ── Flush on unmount / page change ───────────────────────────────────────
  useEffect(() => {
    return () => {
      saveAnnotations(recipeId, pageKey, strokesRef.current).catch(console.error);
    };
  }, [recipeId, pageKey]);

  // ── Size canvas to container width, preserve aspect ratio ────────────────
  const sizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img    = imageRef.current;
    const wrap   = containerRef.current;
    if (!canvas || !img || !wrap) return;

    const displayW = wrap.offsetWidth || 600;
    const displayH = Math.round(displayW * img.naturalHeight / img.naturalWidth);

    // Only resize if dimensions changed (avoids clearing on every render)
    if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
      // Canvas buffer = natural size for full-resolution annotation coords
      canvas.width  = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
    // CSS display size = container width
    canvas.style.width  = displayW + 'px';
    canvas.style.height = displayH + 'px';
  }, []);

  // ── Draw image + all strokes ──────────────────────────────────────────────
  const redraw = useCallback((strokeList, liveStroke) => {
    const canvas = canvasRef.current;
    const img    = imageRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    strokeList.forEach(s => paintStroke(ctx, s));
    if (liveStroke) paintStroke(ctx, liveStroke);
  }, []);

  // Trigger size + redraw when image loads or strokes change
  useEffect(() => {
    if (!ready) return;
    sizeCanvas();
    redraw(strokes);
  }, [ready, strokes, sizeCanvas, redraw]);

  // Resize when container width changes (e.g. sidebar toggled, window resize)
  useEffect(() => {
    const wrap = containerRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => {
      if (ready) { sizeCanvas(); redraw(strokesRef.current); }
    });
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [ready, sizeCanvas, redraw]);

  function paintStroke(ctx, stroke) {
    if (!stroke.points || stroke.points.length < 2) return;
    ctx.save();
    ctx.globalAlpha = stroke.opacity;
    ctx.strokeStyle = stroke.color;
    ctx.lineWidth   = stroke.size;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
    for (let i = 1; i < stroke.points.length; i++) {
      const p = stroke.points[i-1], q = stroke.points[i];
      ctx.quadraticCurveTo(p.x, p.y, (p.x+q.x)/2, (p.y+q.y)/2);
    }
    ctx.stroke();
    ctx.restore();
  }

  // Convert screen coordinates → canvas buffer coordinates
  function getPos(e) {
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    const scaleX = canvas.width  / rect.width;
    const scaleY = canvas.height / rect.height;
    const src    = e.touches ? e.touches[0] : e;
    return {
      x: (src.clientX - rect.left) * scaleX,
      y: (src.clientY - rect.top)  * scaleY,
    };
  }

  const onDown = useCallback((e) => {
    if (!toolbarOpen) return;
    e.preventDefault();
    drawing.current     = true;
    currentPath.current = [getPos(e)];
  }, [toolbarOpen]);

  const onMove = useCallback((e) => {
    if (!drawing.current) return;
    e.preventDefault();
    currentPath.current.push(getPos(e));
    redraw(strokes, { tool, color, size, opacity, points: currentPath.current });
  }, [strokes, tool, color, size, opacity, redraw]);

  const onUp = useCallback(() => {
    if (!drawing.current) return;
    drawing.current = false;
    if (currentPath.current.length < 2) return;
    const next = [...strokes, { tool, color, size, opacity, points: currentPath.current }];
    currentPath.current = [];
    setStrokes(next);
    saveAnnotations(recipeId, pageKey, next).catch(console.error);
  }, [strokes, tool, color, size, opacity, recipeId, pageKey]);

  const handleUndo = () => {
    const next = strokes.slice(0, -1);
    setStrokes(next);
    saveAnnotations(recipeId, pageKey, next).catch(console.error);
  };
  const handleClear = async () => {
    setStrokes([]);
    await clearAnnotations(recipeId, pageKey).catch(console.error);
    if (ready) { sizeCanvas(); redraw([], null); }
  };
  const switchTool = (nt) => {
    setTool(nt);
    setSize(DEFAULTS[nt].size);
    setOpacity(DEFAULTS[nt].opacity);
    setColor(DEFAULTS[nt].color);
  };

  return (
    <div ref={containerRef} className="iac-wrap">
      <canvas
        ref={canvasRef}
        className={`iac-canvas ${toolbarOpen ? 'drawing' : ''}`}
        onMouseDown={onDown}   onMouseMove={onMove}
        onMouseUp={onUp}       onMouseLeave={onUp}
        onTouchStart={onDown}  onTouchMove={onMove}  onTouchEnd={onUp}
      />
      <AnnotationToolbar
        t={t} tool={tool} color={color} size={size} opacity={opacity}
        toolbarOpen={toolbarOpen} strokes={strokes}
        onToggle={() => setToolbarOpen(o => !o)}
        onSwitchTool={switchTool}
        onColorChange={setColor} onSizeChange={setSize} onOpacityChange={setOpacity}
        onUndo={handleUndo} onClear={handleClear}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PdfAnnotationLayer
   Transparent canvas over the PDF iframe. Drawing mode intercepts touches;
   normal mode lets the PDF iframe scroll.
───────────────────────────────────────────────────────────────────────────── */
export function PdfAnnotationLayer({ recipeId, pageKey }) {
  const { t } = useApp();
  const canvasRef   = useRef(null);
  const drawing     = useRef(false);
  const currentPath = useRef([]);

  const [strokes, setStrokes]         = useState([]);
  const [tool, setTool]               = useState('pencil');
  const [color, setColor]             = useState(DEFAULTS.pencil.color);
  const [size, setSize]               = useState(DEFAULTS.pencil.size);
  const [opacity, setOpacity]         = useState(DEFAULTS.pencil.opacity);
  const [toolbarOpen, setToolbarOpen] = useState(false);

  const strokesRef = useRef(strokes);
  useEffect(() => { strokesRef.current = strokes; }, [strokes]);

  useEffect(() => {
    if (!recipeId || !pageKey) return;
    fetchAnnotations(recipeId, pageKey).then(setStrokes).catch(() => {});
  }, [recipeId, pageKey]);

  useEffect(() => {
    return () => {
      saveAnnotations(recipeId, pageKey, strokesRef.current).catch(console.error);
    };
  }, [recipeId, pageKey]);

  // Keep canvas pixel size = its CSS display size
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      repaint(strokesRef.current);
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { repaint(strokes); }, [strokes]);

  function repaint(list, live) {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.width) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    list.forEach(s => paintStroke(ctx, s));
    if (live) paintStroke(ctx, live);
  }

  function paintStroke(ctx, stroke) {
    if (!stroke.points || stroke.points.length < 2) return;
    ctx.save();
    ctx.globalAlpha = stroke.opacity;
    ctx.strokeStyle = stroke.color;
    ctx.lineWidth   = stroke.size;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
    for (let i = 1; i < stroke.points.length; i++) {
      const p = stroke.points[i-1], q = stroke.points[i];
      ctx.quadraticCurveTo(p.x, p.y, (p.x+q.x)/2, (p.y+q.y)/2);
    }
    ctx.stroke();
    ctx.restore();
  }

  function getPos(e) {
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    const src    = e.touches ? e.touches[0] : e;
    return { x: src.clientX - rect.left, y: src.clientY - rect.top };
  }

  const onDown = useCallback((e) => {
    e.preventDefault(); drawing.current = true; currentPath.current = [getPos(e)];
  }, []);
  const onMove = useCallback((e) => {
    if (!drawing.current) return;
    e.preventDefault();
    currentPath.current.push(getPos(e));
    repaint(strokes, { tool, color, size, opacity, points: currentPath.current });
  }, [strokes, tool, color, size, opacity]);
  const onUp = useCallback(() => {
    if (!drawing.current) return;
    drawing.current = false;
    if (currentPath.current.length < 2) return;
    const next = [...strokes, { tool, color, size, opacity, points: currentPath.current }];
    currentPath.current = [];
    setStrokes(next);
    saveAnnotations(recipeId, pageKey, next).catch(console.error);
  }, [strokes, tool, color, size, opacity, recipeId, pageKey]);

  const handleUndo = () => {
    const next = strokes.slice(0, -1);
    setStrokes(next);
    saveAnnotations(recipeId, pageKey, next).catch(console.error);
  };
  const handleClear = async () => {
    setStrokes([]);
    await clearAnnotations(recipeId, pageKey).catch(console.error);
  };
  const switchTool = (nt) => {
    setTool(nt); setSize(DEFAULTS[nt].size);
    setOpacity(DEFAULTS[nt].opacity); setColor(DEFAULTS[nt].color);
  };

  return (
    <div className="pdf-annotation-layer">
      <canvas
        ref={canvasRef}
        className={`pdf-annotation-canvas ${toolbarOpen ? 'drawing' : ''}`}
        onMouseDown={toolbarOpen ? onDown : undefined}
        onMouseMove={toolbarOpen ? onMove : undefined}
        onMouseUp={toolbarOpen   ? onUp   : undefined}
        onMouseLeave={toolbarOpen ? onUp  : undefined}
        onTouchStart={toolbarOpen ? onDown : undefined}
        onTouchMove={toolbarOpen  ? onMove : undefined}
        onTouchEnd={toolbarOpen   ? onUp   : undefined}
      />
      <AnnotationToolbar
        t={t} tool={tool} color={color} size={size} opacity={opacity}
        toolbarOpen={toolbarOpen} strokes={strokes}
        onToggle={() => setToolbarOpen(o => !o)}
        onSwitchTool={switchTool}
        onColorChange={setColor} onSizeChange={setSize} onOpacityChange={setOpacity}
        onUndo={handleUndo} onClear={handleClear}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Shared toolbar
───────────────────────────────────────────────────────────────────────────── */
function AnnotationToolbar({
  t, tool, color, size, opacity, toolbarOpen, strokes,
  onToggle, onSwitchTool, onColorChange, onSizeChange, onOpacityChange,
  onUndo, onClear,
}) {
  return (
    <>
      <button
        className={`annotation-toggle ${toolbarOpen ? 'active' : ''} ${strokes.length > 0 ? 'has-marks' : ''}`}
        onClick={onToggle}
      >
        <Pencil size={16} />
        {strokes.length > 0 && <span className="annotation-dot" />}
        {toolbarOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {toolbarOpen && (
        <div className="annotation-toolbar">
          <div className="at-group">
            <button className={`at-tool-btn ${tool==='pencil'?'active':''}`} onClick={() => onSwitchTool('pencil')}>
              <Pencil size={16}/><span>{t('pencilTool')}</span>
            </button>
            <button className={`at-tool-btn ${tool==='highlight'?'active':''}`} onClick={() => onSwitchTool('highlight')}>
              <Highlighter size={16}/><span>{t('highlightTool')}</span>
            </button>
          </div>
          <div className="at-divider"/>
          <div className="at-group at-colors">
            {PRESET_COLORS.map(c => (
              <button key={c} className={`at-color-btn ${color===c?'active':''}`}
                style={{background:c}} onClick={() => onColorChange(c)}/>
            ))}
            <label className="at-color-custom">
              <input type="color" value={color} onChange={e => onColorChange(e.target.value)}/>
              <span style={{background:color}} className={`at-color-btn ${!PRESET_COLORS.includes(color)?'active':''}`}/>
            </label>
          </div>
          <div className="at-divider"/>
          <div className="at-group at-sliders">
            <label className="at-slider-label">
              <span>{t('sizeLabel')}</span><span className="at-slider-val">{size}px</span>
            </label>
            <input type="range" min={1} max={60} value={size}
              onChange={e => onSizeChange(Number(e.target.value))} className="at-slider"/>
          </div>
          <div className="at-group at-sliders">
            <label className="at-slider-label">
              <span>{t('opacityLabel')}</span><span className="at-slider-val">{Math.round(opacity*100)}%</span>
            </label>
            <input type="range" min={5} max={100} value={Math.round(opacity*100)}
              onChange={e => onOpacityChange(Number(e.target.value)/100)} className="at-slider"/>
          </div>
          <div className="at-divider"/>
          <div className="at-group at-actions">
            <button className="at-action-btn" onClick={onUndo} disabled={strokes.length===0}>
              <RotateCcw size={15}/><span>{t('undoStroke')}</span>
            </button>
            <button className="at-action-btn danger" onClick={onClear} disabled={strokes.length===0}>
              <Trash2 size={15}/><span>{t('clearAll')}</span>
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default ImageAnnotationCanvas;
