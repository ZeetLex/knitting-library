/**
 * CurrencyInput
 * A number input with the user's currency symbol as a fixed prefix.
 * Stores plain numeric strings (e.g. "249") — no currency suffix needed.
 *
 * Legacy values (e.g. "ca. 100kr", "69 NOK") are silently cleaned to just
 * the numeric part so old database entries never cause a crash or blank field.
 *
 * Usage:
 *   <CurrencyInput value={price} onChange={setPrice} placeholder="0" />
 */
import React, { useEffect, useState } from 'react';
import { useApp } from '../utils/AppContext';
import './CurrencyInput.css';

// Extract the first number from a string — handles "ca. 100kr", "69 NOK", "£49", "249", etc.
function toNumericString(raw) {
  if (raw === null || raw === undefined) return '';
  const s = String(raw).trim();
  if (s === '') return '';
  // Already a plain number (integer or decimal)
  if (/^\d+(\.\d+)?$/.test(s)) return s;
  // Extract digits (and optional decimal point) from anywhere in the string
  const match = s.match(/(\d+(?:[.,]\d+)?)/);
  if (!match) return '';
  // Normalise comma decimals → dot
  return match[1].replace(',', '.');
}

export default function CurrencyInput({
  value, onChange, placeholder = '0', className = '', disabled = false
}) {
  const { currencySymbol } = useApp();

  // Internal display value — cleaned from legacy strings on first render
  const [internal, setInternal] = useState(() => toNumericString(value));

  // Sync when the parent value changes (e.g. form resets, different item loaded)
  useEffect(() => {
    setInternal(toNumericString(value));
  }, [value]);

  const handleChange = (e) => {
    const raw = e.target.value;
    setInternal(raw);
    onChange(raw);
  };

  return (
    <div className={`currency-input-wrap ${className}`}>
      <span className="currency-input-symbol">{currencySymbol}</span>
      <input
        type="number"
        inputMode="decimal"
        min="0"
        step="any"
        className="currency-input-field"
        value={internal}
        onChange={handleChange}
        placeholder={placeholder}
        disabled={disabled}
      />
    </div>
  );
}
