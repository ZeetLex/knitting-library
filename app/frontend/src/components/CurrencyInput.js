/**
 * CurrencyInput
 * A number input with the user's currency symbol as a fixed prefix.
 * Stores plain numeric strings (e.g. "249") — no currency suffix needed.
 *
 * Usage:
 *   <CurrencyInput value={price} onChange={setPrice} placeholder="0" />
 */
import React from 'react';
import { useApp } from '../utils/AppContext';
import './CurrencyInput.css';

export default function CurrencyInput({ value, onChange, placeholder = '0', className = '', disabled = false }) {
  const { currencySymbol } = useApp();
  return (
    <div className={`currency-input-wrap ${className}`}>
      <span className="currency-input-symbol">{currencySymbol}</span>
      <input
        type="number"
        inputMode="decimal"
        min="0"
        step="any"
        className="currency-input-field"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
    </div>
  );
}
