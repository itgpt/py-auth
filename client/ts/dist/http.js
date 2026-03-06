"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.postJson = postJson;
async function postJson(url, body, timeoutMs) {
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
        let json = null;
        try {
            json = text ? JSON.parse(text) : null;
        }
        catch {
            json = null;
        }
        return { status: res.status, json, text };
    }
    finally {
        clearTimeout(timer);
    }
}
