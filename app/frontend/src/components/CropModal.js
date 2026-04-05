import React, { useState, useRef, useCallback, useEffect } from 'react';
import { X } from 'lucide-react';
import { imageUrl } from '../utils/api';
import './CropModal.css';

/**
 * 4-point perspective crop modal.
 * Props:
 *   recipeId     – recipe ID (used to build the image URL)
 *   filename     – image filename
 *   imageVersion – optional cache-bust value (timestamp or thumbnail_version)
 *   t            – translation function
 *   onClose      – called when the user cancels
 *   onCrop(points) – called with [[x,y]×4] in TL,TR,BR,BL order (original px)
 */
export default function CropModal({ t, recipeId, filename, imageVersion, onClose, onCrop }) {
  const canvasRef = useRef(null);
  const imgRef    = useRef(null);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [saving, setSaving]       = useState(false);

  const handles     = useRef(null);  // [TL, TR, BR, BL] in display px
  const dragging    = useRef(null);  // index being dragged or null
  const naturalSize = useRef({ w: 1, h: 1 });
  const displaySize = useRef({ w: 1, h: 1, scale: 1 });

  const imgSrc = imageUrl(recipeId, filename, imageVersion);

  /* ── Draw the canvas overlay ── */
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !handles.current) return;
    const ctx = canvas.getContext('2d');
    const { w, h } = displaySize.current;
    ctx.clearRect(0, 0, w, h);

    const [tl, tr, br, bl] = handles.current;

    // Dark mask
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(0, 0, w, h);

    // Cut out the selected quad
    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.moveTo(tl.x, tl.y);
    ctx.lineTo(tr.x, tr.y);
    ctx.lineTo(br.x, br.y);
    ctx.lineTo(bl.x, bl.y);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // Quad border
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(tl.x, tl.y);
    ctx.lineTo(tr.x, tr.y);
    ctx.lineTo(br.x, br.y);
    ctx.lineTo(bl.x, bl.y);
    ctx.closePath();
    ctx.stroke();

    // Handles
    handles.current.forEach((pt) => {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 11, 0, Math.PI * 2);
      ctx.fillStyle = 'white';
      ctx.fill();
      ctx.strokeStyle = 'rgba(180,80,80,0.9)';
      ctx.lineWidth = 2.5;
      ctx.stroke();
    });
  }, []); // intentional

  /* ── Init handles when image loads ── */
  const onImgLoad = useCallback(() => {
    const img    = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;

    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    naturalSize.current = { w: natW, h: natH };

    // wrapPad must match the CSS padding on .crop-canvas-wrap so the image
    // never fills right to the edge and corner handles stay reachable by thumb.
    const isMobile = window.innerWidth < 641;
    const wrapPad  = isMobile ? 44 : 24;  // px — same value as CSS below
    const maxW  = Math.min(window.innerWidth  * 0.95, 900) - wrapPad * 2;
    const maxH  = Math.min(window.innerHeight * 0.85, 700) - wrapPad * 2;
    const scale = Math.min(maxW / natW, maxH / natH, 1);
    const dispW = Math.round(natW * scale);
    const dispH = Math.round(natH * scale);
    displaySize.current = { w: dispW, h: dispH, scale };

    canvas.width        = dispW;
    canvas.height       = dispH;
    img.style.width     = dispW + 'px';
    img.style.height    = dispH + 'px';

    const pad = 8;
    handles.current = [
      { x: pad,         y: pad         },  // TL
      { x: dispW - pad, y: pad         },  // TR
      { x: dispW - pad, y: dispH - pad }, // BR
      { x: pad,         y: dispH - pad }, // BL
    ];

    setImgLoaded(true);
    draw();
  }, [draw]);

  useEffect(() => { if (imgLoaded) draw(); }, [imgLoaded, draw]);

  /* ── Pointer helpers ── */
  const getPos = (e) => {
    const rect    = canvasRef.current.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const hitTest = (pos) => handles.current.findIndex(pt =>
    Math.hypot(pt.x - pos.x, pt.y - pos.y) < 20
  );

  const onPointerDown = (e) => {
    if (!handles.current) return;
    e.preventDefault();
    const idx = hitTest(getPos(e));
    if (idx !== -1) dragging.current = idx;
  };

  const onPointerMove = (e) => {
    if (dragging.current === null || !handles.current) return;
    e.preventDefault();
    const { w, h } = displaySize.current;
    const pos = getPos(e);
    handles.current[dragging.current] = {
      x: Math.max(0, Math.min(w, pos.x)),
      y: Math.max(0, Math.min(h, pos.y)),
    };
    draw();
  };

  const onPointerUp = () => { dragging.current = null; };

  /* ── Submit ── */
  const handleConfirm = async () => {
    if (!handles.current) return;
    const scale = displaySize.current.scale;
    const points = handles.current.map(pt => [
      Math.round(pt.x / scale),
      Math.round(pt.y / scale),
    ]);
    setSaving(true);
    await onCrop(points);
    setSaving(false);
  };

  return (
    <div className="modal-overlay crop-modal-overlay" onClick={onClose}>
      <div className="crop-modal" onClick={e => e.stopPropagation()}>
        <div className="crop-modal-header">
          <h3>{t('cropImage') || 'Crop Image'}</h3>
          <p className="crop-modal-hint">{t('cropHint') || 'Drag the four corners to define the crop area.'}</p>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>

        <div className="crop-canvas-wrap">
          <img
            ref={imgRef}
            src={imgSrc}
            alt="crop"
            className="crop-base-img"
            onLoad={onImgLoad}
            draggable={false}
          />
          <canvas
            ref={canvasRef}
            className="crop-overlay-canvas"
            onMouseDown={onPointerDown}
            onMouseMove={onPointerMove}
            onMouseUp={onPointerUp}
            onMouseLeave={onPointerUp}
            onTouchStart={onPointerDown}
            onTouchMove={onPointerMove}
            onTouchEnd={onPointerUp}
          />
        </div>

        <div className="crop-modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            {t('cancel') || 'Cancel'}
          </button>
          <button className="btn-primary" onClick={handleConfirm} disabled={saving || !imgLoaded}>
            {saving ? '…' : (t('applyCrop') || 'Apply Crop')}
          </button>
        </div>
      </div>
    </div>
  );
}
