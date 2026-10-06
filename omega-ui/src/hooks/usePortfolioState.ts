import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

export const useExecutionBlotter = () => useQuery({
  queryKey: ['execution-blotter'], queryFn: apiClient.getExecutionBlotter, retry: false,
});
