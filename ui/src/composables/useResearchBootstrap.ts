import { onScopeDispose, ref } from 'vue';
import { researchFailureMessage, temporaryResearchFailure } from '@/utils/researchConnection';

/** Bounded retries for initial read-only loading. Never reuse this for a research/trading command. */
export function useResearchBootstrap(read: (context: { isCurrent: () => boolean }) => Promise<void>) {
  const phase = ref<'idle' | 'loading' | 'waiting' | 'ready' | 'failed'>('idle');
  const attempt = ref(0), error = ref('');
  const maxAttempts = 3;
  let generation = 0, disposed = false, timer: ReturnType<typeof setTimeout> | undefined;
  function clearTimer() { if (timer !== undefined) clearTimeout(timer); timer = undefined; }
  async function run(current: number) {
    if (disposed || current!==generation) return;
    attempt.value++; phase.value = 'loading';
    const isCurrent = () => !disposed && current === generation;
    try {
      await read({ isCurrent });
      if (isCurrent()) { phase.value = 'ready'; error.value = ''; }
    } catch (problem) {
      if (!isCurrent()) return;
      error.value = researchFailureMessage(problem);
      if (temporaryResearchFailure(problem) && attempt.value < maxAttempts) {
        phase.value = 'waiting';
        timer = setTimeout(() => { timer = undefined; void run(current); }, attempt.value === 1 ? 1000 : 3000);
      } else phase.value = 'failed';
    }
  }
  async function start() {
    if (disposed || phase.value === 'loading' || phase.value === 'ready') return;
    clearTimer(); attempt.value = 0; error.value = '';
    await run(++generation);
  }
  onScopeDispose(() => { disposed = true; generation++; clearTimer(); });
  return { phase, attempt, error, maxAttempts, start };
}
