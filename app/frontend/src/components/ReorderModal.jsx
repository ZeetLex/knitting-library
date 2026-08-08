import React, { useState } from 'react';
import { ChevronUp, ChevronDown, GripVertical, X } from 'lucide-react';
import { imageUrl, saveImageOrder } from '../utils/api';

export default function ReorderModal({ t, recipeId, images, onClose, onSaved }) {
  const [order, setOrder]           = useState([...images]);
  const [dragIdx, setDragIdx]       = useState(null);   // which row is being dragged
  const [dropIdx, setDropIdx]       = useState(null);   // which row the drag is over
  const [saving, setSaving]         = useState(false);
  const [saved, setSaved]           = useState(false);

  const moveItem = (idx, dir) => {
    const target = idx + dir;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    [next[idx], next[target]] = [next[target], next[idx]];
    setOrder(next);
  };

  const handleDragStart = (e, i) => {
    // Store the source index both in state and in dataTransfer as a fallback
    setDragIdx(i);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(i));
  };

  const handleDragOver = (e, i) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dropIdx !== i) setDropIdx(i);
  };

  // Only commit the reorder on drop — avoids re-render mid-drag breaking the drag
  const handleDrop = (e, i) => {
    e.preventDefault();
    const from = dragIdx ?? parseInt(e.dataTransfer.getData('text/plain'), 10);
    setDragIdx(null);
    setDropIdx(null);
    if (isNaN(from) || from === i) return;
    const next = [...order];
    const [moved] = next.splice(from, 1);
    next.splice(i, 0, moved);
    setOrder(next);
  };

  const handleDragEnd = () => { setDragIdx(null); setDropIdx(null); };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await saveImageOrder(recipeId, order);
      setSaved(true);
      setTimeout(() => onSaved(order, result), 700);
    } catch (e) {
      alert('Failed to save order.');
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay modal-overlay--bottom-mobile" onClick={onClose}>
      <div className="reorder-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{t('reorderTitle')}</h3>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>
        <p className="reorder-help">{t('reorderHelp')}</p>
        <div className="reorder-list">
          {order.map((img, i) => (
            <div
              key={img}
              className={`reorder-item${
                dragIdx === i  ? ' reorder-item--dragging'    :
                dropIdx  === i ? ' reorder-item--drop-target' : ''
              }`}
              draggable
              onDragStart={e => handleDragStart(e, i)}
              onDragOver={e  => handleDragOver(e, i)}
              onDrop={e      => handleDrop(e, i)}
              onDragLeave={() => setDropIdx(null)}
              onDragEnd={handleDragEnd}
            >
              <GripVertical size={18} className="reorder-grip" />
              <span className="reorder-num">{i + 1}</span>
              <img
                className="reorder-thumb"
                src={imageUrl(recipeId, img)}
                alt={`Image ${i + 1}`}
                loading="lazy"
                draggable={false}
              />
              <span className="reorder-name">{img}</span>
              <div className="reorder-arrows">
                <button
                  className="reorder-arrow"
                  onClick={() => moveItem(i, -1)}
                  disabled={i === 0}
                  title="Move up"
                ><ChevronUp size={15} /></button>
                <button
                  className="reorder-arrow"
                  onClick={() => moveItem(i, 1)}
                  disabled={i === order.length - 1}
                  title="Move down"
                ><ChevronDown size={15} /></button>
              </div>
            </div>
          ))}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || saved}>
            {saved ? t('orderSaved') : saving ? '…' : t('saveOrder')}
          </button>
        </div>
      </div>
    </div>
  );
}
