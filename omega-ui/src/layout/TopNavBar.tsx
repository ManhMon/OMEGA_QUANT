import React from 'react';
import { useTranslation } from '../i18n';
import { useUiStore } from '../store/uiStore';
import { useControlOps } from '../hooks/useControlOps';
import { Bot, Activity } from 'lucide-react';

export const TopNavBar: React.FC = () => {
  const { t } = useTranslation();
  const isStreamingConnected = useUiStore((state) => state.isStreamingConnected);
  const locale = useUiStore((state) => state.locale);
  const toggleLocale = useUiStore((state) => state.toggleLocale);
  const digitShortcutsEnabled = useUiStore((state) => state.digitShortcutsEnabled);
  const setDigitShortcutsEnabled = useUiStore((state) => state.setDigitShortcutsEnabled);
  
  const isCopilotDrawerOpen = useUiStore((state) => state.isCopilotDrawerOpen);
  const setIsCopilotDrawerOpen = useUiStore((state) => state.setIsCopilotDrawerOpen);
  
  const { tasks, isDrawerOpen, setIsDrawerOpen } = useControlOps();
  const taskCount = Object.keys(tasks).length;

  return (
    <header className="h-14 border-b border-white/10 bg-zinc-950/95 backdrop-blur-md px-6 flex items-center justify-between font-mono select-none z-30 shrink-0 shadow-lg">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-black tracking-widest bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent flex items-center gap-3">
          OMEGA <span className="text-zinc-600 opacity-50">|</span> <span className="text-zinc-100">QUANT</span>
        </h1>
        <div className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-lg bg-zinc-900 border border-white/5">
          <div className={`w-2 h-2 rounded-full ${isStreamingConnected ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-amber-400'}`} />
          <span className="text-xs font-bold text-zinc-300 tracking-wider">
            {isStreamingConnected ? t.common.online : t.common.standby}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-xs font-bold text-zinc-400 cursor-pointer hover:text-zinc-200 transition-colors">
          <input 
            type="checkbox" 
            checked={digitShortcutsEnabled} 
            onChange={(event) => setDigitShortcutsEnabled(event.target.checked)} 
            className="accent-cyan-400 w-3.5 h-3.5" 
          />
          {t.topNav.enableDigitShortcuts}
        </label>
        
        <button 
          type="button" 
          onClick={toggleLocale} 
          aria-label={t.topNav.language} className="rounded-lg px-3 py-1.5 text-xs font-bold border border-white/10 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-300 transition-colors shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"
        >
          <span lang="vi" className={locale === 'vi' ? 'text-white' : 'opacity-50'}>{t.topNav.langVi}</span>
          <span className="opacity-40 mx-1">/</span>
          <span lang="en" className={locale === 'en' ? 'text-white' : 'opacity-50'}>{t.topNav.langEn}</span>
        </button>
        
        <button
          type="button"
          aria-expanded={isDrawerOpen}
          onClick={() => setIsDrawerOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-950/40 hover:bg-cyan-900/60 text-xs font-bold text-cyan-300 hover:text-cyan-200 transition-colors shadow-sm group"
        >
          <Activity className="w-3.5 h-3.5 group-hover:text-cyan-100 transition-colors" />
          {t.topNav.ops} ({taskCount})
          
        </button>
        
        <button 
          type="button" 
          onClick={() => setIsCopilotDrawerOpen(!isCopilotDrawerOpen)} 
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-950/40 hover:bg-emerald-900/60 text-xs font-bold text-emerald-300 hover:text-emerald-200 transition-colors shadow-sm group"
        >
          <Bot className="w-3.5 h-3.5 group-hover:text-emerald-100 transition-colors" />
          {t.topNav.copilot}
        </button>
        
        <button 
          type="button" 
          onClick={() => useUiStore.getState().setIsConfigModalOpen(true)} 
          className="p-1.5 rounded-lg border border-white/10 bg-zinc-900/90 hover:bg-zinc-800 text-zinc-300 hover:text-white transition-colors shadow-sm"
          aria-label={t.topNav.configuration}
        >
          {t.topNav.configuration}
        </button>
      </div>
    </header>
  );
};




