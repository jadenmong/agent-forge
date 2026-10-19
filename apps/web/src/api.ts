export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('API 尚未就绪，请确认本地服务正在运行。');
  const payload = await response.json();
  if (!response.ok) throw new Error(`${payload.error?.message ?? '请求失败'} (${payload.error?.code ?? response.status})`);
  return payload.data as T;
}
