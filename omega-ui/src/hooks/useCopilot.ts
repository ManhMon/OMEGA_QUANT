import { useState } from 'react';
import type { CopilotExecutedToolItem, CopilotStreamEvent, CopilotSystemSynthesisResponse, RecommendationActionItem } from '../api/client';
import { unavailableMessage } from './useUnavailableQuery';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  textVi: string;
  textEn: string;
  executedTools?: CopilotExecutedToolItem[];
  suggestedActions?: string[];
}

// ponytail: no provider/tool dispatch until the validated Copilot adapter is restored.
export function useCopilot(_enabled: boolean) {
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const sendQuery = (_query: string) => setChatHistory([{
    id: 'unavailable', sender: 'assistant', timestamp: new Date().toISOString(),
    textVi: unavailableMessage, textEn: unavailableMessage,
  }]);
  return {
    synthesis: undefined as CopilotSystemSynthesisResponse | undefined,
    isSynthesisLoading: false, isUnavailable: true,
    refetchSynthesis: () => sendQuery(''),
    recommendations: [] as RecommendationActionItem[],
    chatHistory, isAsking: false, sendQuery,
    clearChat: () => setChatHistory([]),
    dispatchAction: (_action: RecommendationActionItem) => sendQuery(''),
    executingActionId: null as string | null,
    streamEvents: [] as CopilotStreamEvent[], isSseConnected: false,
  };
}
