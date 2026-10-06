import { useQuery } from '@tanstack/react-query';

export const unavailableMessage = 'This integration is unavailable in this build.';

// ponytail: fail-closed recovery stubs; replace with validated API adapters when restored.
export async function unavailable<T>(): Promise<T> {
  throw new Error(unavailableMessage);
}

export function useUnavailableQuery<T>(queryKey: readonly unknown[]) {
  return useQuery<T>({ queryKey, queryFn: unavailable<T>, retry: false });
}
