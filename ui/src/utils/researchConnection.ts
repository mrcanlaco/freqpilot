import type { AxiosInstance } from 'axios';

export class ResearchConnectionError extends Error {
  constructor(message: string, readonly retryable: boolean) { super(message); }
}
export function temporaryResearchFailure(error: unknown): boolean {
  if (error instanceof ResearchConnectionError) return error.retryable;
  const e = error as { code?: string; message?: string; response?: { status?: number } };
  if (e?.response?.status && e.response.status < 500) return false;
  return [500, 502, 503, 504].includes(e?.response?.status ?? 0) ||
    ['ERR_NETWORK', 'ECONNABORTED', 'ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT'].includes(e?.code ?? '') ||
    /network error|timeout/i.test(e?.message ?? '');
}
export function researchFailureMessage(error: unknown): string {
  if (error instanceof ResearchConnectionError) return error.message;
  const status=(error as {response?:{status?:number}})?.response?.status;
  if (status===401) return 'Phiên đăng nhập của dịch vụ nghiên cứu cần được xác thực lại trong cài đặt kết nối.';
  if (status===403) return 'Dịch vụ từ chối đọc workspace. Kiểm tra quyền truy cập và cấu hình paper của kết nối nghiên cứu.';
  if (temporaryResearchFailure(error)) return 'Chưa đọc được dữ liệu nghiên cứu. Dịch vụ có thể đang khởi động lại hoặc kết nối bị gián đoạn.';
  return 'Chưa tải được dữ liệu workspace. Kiểm tra dịch vụ nghiên cứu rồi thử kết nối lại.';
}
type ResearchBot = { botId: string; isWebserverMode: boolean; getState: () => Promise<unknown> };

/** Only probes configured connections with existing authentication. No active-bot selection or writes. */
export async function discoverResearchConnection<T extends ResearchBot>(
  bots: T[], apiFor: (bot: T) => Pick<AxiosInstance, 'get'>,
  preferredId?: string, isCurrent: () => boolean = () => true,
): Promise<T> {
  if (!bots.length) throw new ResearchConnectionError('Chưa có kết nối nghiên cứu. Mở cài đặt để thêm dịch vụ Backtest.', false);
  const probes = await Promise.allSettled(bots.map(bot => bot.getState()));
  if (!isCurrent()) throw new ResearchConnectionError('Đã rời trang nghiên cứu.', false);
  const errors = probes.filter((p): p is PromiseRejectedResult => p.status === 'rejected').map(p => p.reason);
  const candidates = bots.filter((bot, i) => bot.isWebserverMode &&
    (probes[i]?.status === 'fulfilled' || temporaryResearchFailure((probes[i] as PromiseRejectedResult).reason)));
  candidates.sort((a, b) => Number(b.botId === preferredId) - Number(a.botId === preferredId));
  for (const bot of candidates) {
    if (!isCurrent()) throw new ResearchConnectionError('Đã rời trang nghiên cứu.', false);
    try {
      const { data } = await apiFor(bot).get('/studio/library');
      if (!isCurrent()) throw new ResearchConnectionError('Đã rời trang nghiên cứu.', false);
      if (data?.product === 'FreqPilot' && data.engine === '2026.9' && data.dry_run === true && Array.isArray(data.strategies)) return bot;
    } catch (error) { errors.push(error); }
  }
  if (errors.some(temporaryResearchFailure)) throw new ResearchConnectionError('Dịch vụ nghiên cứu chưa sẵn sàng. Có thể dịch vụ đang khởi động lại hoặc kết nối bị gián đoạn.', true);
  if (errors.some(e => e?.response?.status===401)) throw new ResearchConnectionError('Có kết nối chưa xác thực được. Kiểm tra phiên đăng nhập của dịch vụ Backtest trong cài đặt.', false);
  if (errors.some(e => e?.response?.status===403)) throw new ResearchConnectionError('Dịch vụ từ chối đọc workspace. Kiểm tra quyền truy cập và cấu hình paper của kết nối nghiên cứu.', false);
  throw new ResearchConnectionError('Chưa tìm thấy dịch vụ nghiên cứu FreqPilot 2026.9 trong các kết nối hiện có.', false);
}
