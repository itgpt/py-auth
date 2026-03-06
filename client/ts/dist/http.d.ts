export declare function postJson<TResponse>(url: string, body: unknown, timeoutMs: number): Promise<{
    status: number;
    json: TResponse | null;
    text: string;
}>;
