import React from 'react';

const STATUS_STYLES: Record<string, { label: string; classes: string }> = {
  synced: { label: 'Scheduled (T-1h Pending)', classes: 'bg-slate-100 text-slate-700 border-slate-200' },
  pre_capturing: { label: 'Capturing Pre-Change...', classes: 'bg-indigo-100 text-indigo-800 border-indigo-200' },
  pre_captured: { label: 'Pre-Change Captured', classes: 'bg-blue-100 text-blue-800 border-blue-200' },
  post_capturing: { label: 'Comparing Post-Change...', classes: 'bg-amber-100 text-amber-800 border-amber-200' },
  completed: { label: 'Completed & Analyzed', classes: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
  failed: { label: 'Failed', classes: 'bg-red-100 text-red-800 border-red-200' },
  cancelled: { label: 'Cancelled', classes: 'bg-slate-200 text-slate-500 border-slate-300 line-through' },
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const meta = STATUS_STYLES[status] ?? {
    label: status.toUpperCase(),
    classes: 'bg-slate-100 text-slate-700 border-slate-200',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${meta.classes}`}>
      {meta.label}
    </span>
  );
};
