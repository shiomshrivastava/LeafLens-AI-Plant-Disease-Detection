// LeafLens ESP32 -> Supabase latest reading. No user JWT or service-role
// credential is ever stored on the ESP32. Deploy with JWT verification OFF;
// this endpoint uses a separate, strong X-Device-Key shared secret.
const deviceId = "leaflens-demo";
const encoder = new TextEncoder();

function constantTimeEqual(a: string, b: string): boolean {
  const aa = encoder.encode(a);
  const bb = encoder.encode(b);
  let delta = aa.length ^ bb.length;
  for (let i = 0; i < Math.max(aa.length, bb.length); i++) {
    delta |= (aa[i] ?? 0) ^ (bb[i] ?? 0);
  }
  return delta === 0;
}

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json(405, { error: "POST required" });
  const configuredKey = Deno.env.get("LEAFLENS_IOT_KEY")?.trim() ?? "";
  if (configuredKey.length < 32 || configuredKey.toUpperCase().includes("REPLACE")) {
    return json(503, { error: "Device key not configured" });
  }
  if (!constantTimeEqual(req.headers.get("x-device-key") ?? "", configuredKey)) {
    return json(401, { error: "Invalid device key" });
  }
  const contentType = req.headers.get("content-type") ?? "";
  const length = Number(req.headers.get("content-length") ?? "0");
  if (!contentType.startsWith("application/json") || length > 2048) {
    return json(415, { error: "Expected a small JSON body" });
  }

  let payload: unknown;
  try {
    payload = await req.json();
  } catch {
    return json(400, { error: "Invalid JSON" });
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return json(422, { error: "Invalid reading" });
  }
  const data = payload as Record<string, unknown>;
  const temp = data.temperature_c;
  const humidity = data.humidity_percent;
  if (typeof temp !== "number" || !Number.isFinite(temp) || temp < -10 || temp > 60 ||
      typeof humidity !== "number" || !Number.isFinite(humidity) || humidity < 0 || humidity > 100) {
    return json(422, { error: "Out-of-range sensor readings" });
  }

  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "") ?? "";
  const secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!url.startsWith("https://") || !secret) {
    return json(503, { error: "Database not configured" });
  }
  const headers: Record<string, string> = {
    "apikey": secret,
    "content-type": "application/json",
    "prefer": "resolution=merge-duplicates,return=minimal",
  };
  // Legacy service_role JWTs use Bearer. Modern sb_secret_ keys do not.
  if (!secret.startsWith("sb_secret_")) headers.authorization = `Bearer ${secret}`;
  try {
    const response = await fetch(`${url}/rest/v1/leaflens_iot_latest?on_conflict=device_id`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        device_id: deviceId,
        temperature_c: Math.round(temp * 10) / 10,
        humidity_percent: Math.round(humidity * 10) / 10,
        updated_at: new Date().toISOString(),
      }),
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) {
      console.error("IoT database upsert failed:", response.status);
      return json(502, { error: "Could not store reading" });
    }
    return json(200, { received: true });
  } catch (error) {
    console.error("IoT network error:", error instanceof Error ? error.name : "unknown");
    return json(502, { error: "Database unavailable" });
  }
});
