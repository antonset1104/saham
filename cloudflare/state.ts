const MAX_CHUNK_BYTES = 512 * 1024;
const MAX_FILE_BYTES = 64 * 1024 * 1024;

function allowedPath(path: string): boolean {
  if (!path || path.includes("\\") || path.includes("..") || path.startsWith("/")) return false;
  return path === "config_web.json" || path === "preset_kustom.json" ||
    /^Database\/[a-zA-Z0-9_./-]+$/.test(path) ||
    /^Arsip_Data_Harian\/[a-zA-Z0-9_./-]+$/.test(path);
}

function safePath(url: URL): string | null {
  const path = url.searchParams.get("path");
  return path && allowedPath(path) ? path : null;
}

function json(value: unknown, status = 200): Response {
  return Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
}

export async function handleState(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = safePath(url);
  if (url.pathname === "/manifest" && request.method === "GET") {
    const result = await env.STATE_DB.prepare(
      "SELECT path, version, byte_size, sha256, chunk_count, updated_at FROM state_files ORDER BY path"
    ).all();
    return json(result.results);
  }
  if (!path) return json({ error: "invalid path" }, 400);

  if (url.pathname === "/chunk" && request.method === "GET") {
    const index = Number(url.searchParams.get("index"));
    if (!Number.isSafeInteger(index) || index < 0) return json({ error: "invalid index" }, 400);
    const row = await env.STATE_DB.prepare(
      "SELECT c.payload FROM state_chunks c JOIN state_files f ON f.path=c.path AND f.version=c.version WHERE c.path=? AND c.chunk_index=?"
    ).bind(path, index).first<{ payload: number[] }>();
    return row ? new Response(new Uint8Array(row.payload), { headers: { "Cache-Control": "no-store" } }) : json({ error: "missing chunk" }, 404);
  }
  if (url.pathname === "/chunk" && request.method === "PUT") {
    const version = url.searchParams.get("version") ?? "";
    const index = Number(url.searchParams.get("index"));
    if (!/^[a-f0-9-]{36}$/.test(version) || !Number.isSafeInteger(index) || index < 0 || index > 1024) {
      return json({ error: "invalid version or index" }, 400);
    }
    const buffer = await request.arrayBuffer();
    if (buffer.byteLength === 0 || buffer.byteLength > MAX_CHUNK_BYTES) return json({ error: "invalid chunk size" }, 413);
    await env.STATE_DB.prepare(
      "INSERT OR REPLACE INTO state_chunks(path,version,chunk_index,payload) VALUES(?,?,?,?)"
    ).bind(path, version, index, new Uint8Array(buffer)).run();
    return json({ ok: true });
  }
  if (url.pathname === "/commit" && request.method === "POST") {
    const body = await request.json().catch(() => null) as {
      version?: string; byte_size?: number; sha256?: string; chunk_count?: number;
    } | null;
    if (!body || !/^[a-f0-9-]{36}$/.test(body.version ?? "") ||
        !Number.isSafeInteger(body.byte_size) || (body.byte_size ?? 0) > MAX_FILE_BYTES ||
        (body.byte_size ?? 0) <= 0 || !/^[a-f0-9]{64}$/.test(body.sha256 ?? "") ||
        !Number.isSafeInteger(body.chunk_count) || (body.chunk_count ?? 0) < 1 || (body.chunk_count ?? 0) > 1024) {
      return json({ error: "invalid manifest" }, 400);
    }
    const count = await env.STATE_DB.prepare(
      "SELECT COUNT(*) AS n FROM state_chunks WHERE path=? AND version=? AND chunk_index>=0 AND chunk_index<?"
    ).bind(path, body.version, body.chunk_count).first<{ n: number }>();
    if (count?.n !== body.chunk_count) return json({ error: "missing chunks" }, 409);
    await env.STATE_DB.batch([
      env.STATE_DB.prepare("INSERT OR REPLACE INTO state_files(path,version,byte_size,sha256,chunk_count) VALUES(?,?,?,?,?)")
        .bind(path, body.version, body.byte_size, body.sha256, body.chunk_count),
      env.STATE_DB.prepare("DELETE FROM state_chunks WHERE path=? AND version<>?").bind(path, body.version),
    ]);
    return json({ ok: true });
  }
  return json({ error: "not found" }, 404);
}
