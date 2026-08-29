import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { advancedQuantApi, JobStatusResponse, JobSubmitRequest } from '../api/advancedQuant';

const terminal = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTERED']);

export function useDurableJob() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const submit = useMutation({
    mutationFn: ({ request, idempotencyKey }: { request: JobSubmitRequest; idempotencyKey: string }) =>
      advancedQuantApi.submitJob(request, idempotencyKey),
    onSuccess: (accepted) => setJobId(accepted.job_id),
  });
  const status = useQuery({
    queryKey: ['durable-job', jobId],
    queryFn: ({ signal }) => advancedQuantApi.getJob(jobId!, signal),
    enabled: Boolean(jobId),
    refetchInterval: (query) => terminal.has(query.state.data?.status ?? '') ? false : 5000,
  });

  useEffect(() => {
    if (!jobId || terminal.has(status.data?.status ?? '')) return;
    const source = new EventSource(advancedQuantApi.eventUrl(`/api/v1/jobs/${jobId}/events`));
    const handleEvent = () => {
      void queryClient.invalidateQueries({ queryKey: ['durable-job', jobId], refetchType: 'active' });
    };
    source.onmessage = handleEvent;
    source.addEventListener('status', handleEvent);
    source.addEventListener('progress', handleEvent);
    source.addEventListener('complete', handleEvent);
    source.addEventListener('error', handleEvent);
    source.addEventListener('artifact', handleEvent);

    source.onerror = () => source.close();
    return () => {
      source.removeEventListener('status', handleEvent);
      source.removeEventListener('progress', handleEvent);
      source.removeEventListener('complete', handleEvent);
      source.removeEventListener('error', handleEvent);
      source.removeEventListener('artifact', handleEvent);
      source.close();
    };
  }, [jobId, queryClient, status.data?.status]);

  return {
    jobId,
    job: status.data as JobStatusResponse | undefined,
    submit: submit.mutateAsync,
    cancel: () => jobId ? advancedQuantApi.cancelJob(jobId) : Promise.reject(new Error('No active job')),
    isSubmitting: submit.isPending,
    isLoading: status.isLoading,
    error: submit.error ?? status.error,
  };
}
