import React from 'react';
import { Megaphone, X } from 'lucide-react';
import './AnnouncementModal.css';

/**
 * Shows one or more unread announcements to the user.
 * Dismisses all of them when "Got it!" is clicked.
 */
export default function AnnouncementModal({ announcements, onDismiss }) {
  if (!announcements || announcements.length === 0) return null;

  // Show the most recent announcement (first in the sorted list)
  const latest = announcements[0];
  const remaining = announcements.length - 1;

  const formatDate = (iso) => {
    try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
    catch { return iso; }
  };

  return (
    <div className="ann-overlay" role="dialog" aria-modal="true" aria-labelledby="ann-title">
      <div className="ann-modal">
        <div className="ann-header">
          <div className="ann-icon">
            <Megaphone size={20} />
          </div>
          <div className="ann-header-text">
            <span className="ann-label">Update Notes</span>
            <h2 className="ann-title" id="ann-title">{latest.title}</h2>
          </div>
        </div>

        {latest.body && (
          <div className="ann-body">
            <pre className="ann-body-text">{latest.body}</pre>
          </div>
        )}

        <div className="ann-footer">
          <div className="ann-meta">
            {formatDate(latest.created_at)}
            {remaining > 0 && (
              <span className="ann-more"> · +{remaining} more update{remaining > 1 ? 's' : ''}</span>
            )}
          </div>
          <button className="ann-dismiss-btn" onClick={onDismiss} autoFocus>
            Got it!
          </button>
        </div>
      </div>
    </div>
  );
}
