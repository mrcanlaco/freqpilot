import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { getActivePinia } from 'pinia';
import { useFqFleetStore } from '@/datasource/stores/fleet';
import { useFqPrefsStore } from '@/datasource/stores/prefs';
import type { ScopeRef } from '@/datasource/types';
import type { BotMode } from '@/gateway/types.gen';
import { commonCurrency, currencyFromPair, normalizeCurrency } from '@/utils/stakeCurrency';

type Target = {
  botKey?: string | null;
  pair?: string | null;
  botKeys?: readonly string[];
  scope?: ScopeRef;
  mode?: BotMode;
  modes?: readonly BotMode[];
  currencies?: readonly unknown[];
};
/** No guessed stablecoin and no FX conversion. Empty means that the unit is not known. */
export function useStakeCurrency(target?: MaybeRefOrGetter<Target>) {
  const fleet = getActivePinia() ? useFqFleetStore() : null;
  const prefs = getActivePinia() ? useFqPrefsStore() : null;
  return computed(() => {
    const request = target ? toValue(target) : {};
    if (request.currencies) return commonCurrency(request.currencies) ?? '';
    if (request.botKey)
      return (
        normalizeCurrency(fleet?.bots[request.botKey]?.identity.stake_currency) ??
        currencyFromPair(request.pair) ??
        ''
      );
    if (request.pair) return currencyFromPair(request.pair) ?? '';
    let keys = request.botKeys;
    if (request.scope?.kind === 'bot') keys = [request.scope.botKey];
    if (request.scope?.kind === 'bots') keys = request.scope.botKeys;
    if (request.scope?.kind === 'group')
      keys =
        prefs?.settings.fleet.groups.find((g) => g.id === (request.scope as { id: string }).id)
          ?.botKeys ?? [];
    if (keys?.some((key) => !fleet?.bots[key])) return '';
    let rows = fleet?.list ?? [];
    if (keys) rows = rows.filter((b) => keys.includes(b.bot_key));
    else if (!request.scope) {
      const excluded = prefs?.settings.scope.excluded ?? [];
      rows = rows.filter((b) => !excluded.includes(b.bot_key));
    }
    const modes =
      request.modes ??
      (request.mode
        ? [request.mode]
        : !keys &&
            !request.scope &&
            prefs?.settings.scope.mode &&
            prefs.settings.scope.mode !== 'all'
          ? [prefs.settings.scope.mode]
          : undefined);
    if (modes) rows = rows.filter((b) => modes.includes(b.identity.mode));
    return commonCurrency(rows.map((b) => b.identity.stake_currency)) ?? '';
  });
}
