export async function postJson<TResponse>(url: string, body: unknown, timeoutMs: number): Promise<{ status: number; json: TResponse | null; text: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    const text = await res.text();
    let json: TResponse | null = null;
    try {
      json = text ? (JSON.parse(text) as TResponse) : null;
    } catch {
      json = null;
    }

    return { status: res.status, json, text };
  } finally {
    clearTimeout(timer);
  }
}
