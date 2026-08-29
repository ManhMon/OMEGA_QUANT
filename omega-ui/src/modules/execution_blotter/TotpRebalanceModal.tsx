import React, { useState } from 'react';
import { ShieldAlert, Lock, X, AlertTriangle } from 'lucide-react';

interface TotpRebalanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (totpCode: string) => Promise<void>;
  title?: string;
  description?: string;
  actionType?: 'REBALANCE' | 'KILL_SWITCH';
}

export const TotpRebalanceModal: React.FC<TotpRebalanceModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title = 'AUTHORIZE PORTFOLIO REBALANCE',
  description = 'Executing this operation generates live OMS orders across active brokers (VCI, SSI, VNDIRECT). 2FA verification required.',
  actionType = 'REBALANCE'
}) => {
  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.trim().length !== 6 || !/^\d+$/.test(code)) {
      setError('Please enter a valid 6-digit numeric TOTP code.');
      return;
    }

    try {
      setIsSubmitting(true);
      setError('');
      await onConfirm(code);
      setIsSubmitting(false);
      onClose();
    } catch (err: unknown) {
      setIsSubmitting(false);
      setError(err instanceof Error ? err.message : 'Authorization failed');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono select-none">
      <div className="w-full max-w-md bg-zinc-950 border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className={`p-4 border-b flex items-center justify-between ${
          actionType === 'KILL_SWITCH'
            ? 'bg-rose-950/50 border-rose-500/30'
            : 'bg-zinc-900 border-white/10'
        }`}>
          <div className="flex items-center gap-2.5">
            {actionType === 'KILL_SWITCH' ? (
              <ShieldAlert className="w-5 h-5 text-rose-400" />
            ) : (
              <Lock className="w-5 h-5 text-emerald-400" />
            )}
            <h3 className={`text-xs font-bold uppercase tracking-wider ${
              actionType === 'KILL_SWITCH' ? 'text-rose-300' : 'text-zinc-100'
            }`}>
              {title}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-white/10 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4">
          <p className="text-xs text-zinc-300 leading-relaxed">
            {description}
          </p>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold text-zinc-400 flex items-center justify-between">
              <span>Enter 6-Digit TOTP Token:</span>
              <span className="text-[10px] text-zinc-500">Authenticator App</span>
            </label>
            <input
              type="text"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                if (error) setError('');
              }}
              className="w-full text-center text-2xl tracking-[0.5em] font-bold bg-zinc-900 border border-white/10 rounded-xl py-3 text-zinc-100 placeholder:text-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
              autoFocus
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-xs text-rose-400 bg-rose-950/50 p-2.5 rounded-lg border border-rose-500/30">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 mt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-300 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || code.length !== 6}
              className={`px-5 py-2 rounded-lg text-xs font-bold text-zinc-950 transition-all ${
                actionType === 'KILL_SWITCH'
                  ? 'bg-rose-500 hover:bg-rose-400 disabled:opacity-50'
                  : 'bg-emerald-400 hover:bg-emerald-300 disabled:opacity-50'
              }`}
            >
              {isSubmitting ? 'Verifying...' : 'Authorize Execution'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
