import { NextRequest, NextResponse } from 'next/server';
import {
  backendApiBaseUrl,
  clearOperatorSessionCookie,
  operatorSessionFromCookie,
} from '../../../../lib/operator-session';

export const runtime = 'nodejs';

const SAFE_ID = /^[A-Za-z0-9_-]{1,80}$/;
const SAFE_FILENAME = /^[A-Za-z0-9._-]{1,160}$/;

function isAllowedPath(path: string[], method: string): boolean {
  if (
    method === 'GET' &&
    (['social/status', 'social/posts', 'social/summary', 'social/compliance/operations'].includes(path.join('/')) ||
      (path.length === 3 && path[0] === 'social' && path[1] === 'posts' && /^\d+$/.test(path[2])))
  ) return true;
  if (
    method === 'POST' &&
    ['social/compliance/takedowns', 'social/compliance/provider-events'].includes(path.join('/'))
  ) return true;
  if (path.join('/') === 'reports/operator/queue' && method === 'GET') return true;
  if (path.join('/') === 'reports/ground-truth/events' && method === 'GET') return true;
  if (path.length === 3 && path[0] === 'reports' && SAFE_ID.test(path[1])) {
    if (path[2] === 'verification-history' && method === 'GET') return true;
    if (path[2] === 'verification' && method === 'POST') return true;
    if (path[2] === 'verification-evidence' && method === 'POST') return true;
  }
  // Alert management paths
  if (path.length === 1 && path[0] === 'alerts' && (method === 'GET' || method === 'POST')) return true;
  if (path.length === 2 && path[0] === 'alerts' && path[1] === 'config' && method === 'GET') return true;
  if (path.length === 2 && path[0] === 'alerts' && SAFE_ID.test(path[1]) && method === 'GET') return true;
  if (path.length === 3 && path[0] === 'alerts' && SAFE_ID.test(path[1])) {
    if (['recipients', 'deliveries', 'analytics'].includes(path[2]) && method === 'GET') return true;
    if (['approve', 'dispatch', 'cancel'].includes(path[2]) && method === 'POST') return true;
  }
  return false;
}

function isAllowedEvidencePath(path: string[], method: string): boolean {
  return (
    path.length === 4 &&
    path[0] === 'reports' &&
    SAFE_ID.test(path[1]) &&
    path[2] === 'verification-evidence' &&
    SAFE_FILENAME.test(path[3]) &&
    method === 'GET'
  );
}

function sameOrigin(request: NextRequest): boolean {
  return request.headers.get('origin') === request.nextUrl.origin &&
    (process.env.NODE_ENV !== 'production' || request.nextUrl.protocol === 'https:');
}

async function proxy(request: NextRequest, path: string[]) {
  const method = request.method;
  if (!isAllowedPath(path, method) && !isAllowedEvidencePath(path, method)) {
    return NextResponse.json({ detail: 'Operator API route not found.' }, { status: 404 });
  }
  if (method !== 'GET' && !sameOrigin(request)) {
    return NextResponse.json({ detail: 'Cross-origin requests are not allowed.' }, { status: 403 });
  }

  const session = await operatorSessionFromCookie();
  if (!session) {
    await clearOperatorSessionCookie();
    return NextResponse.json({ detail: 'Operator session expired. Please sign in again.' }, { status: 401 });
  }

  const headers = new Headers({ Authorization: `Bearer ${session.token}` });
  let body: ArrayBuffer | undefined;
  if (method !== 'GET') {
    const contentType = request.headers.get('content-type') ?? '';
    if (!contentType.startsWith('application/json') && !contentType.startsWith('multipart/form-data')) {
      return NextResponse.json({ detail: 'Unsupported request content type.' }, { status: 415 });
    }
    body = await request.arrayBuffer();
    if (body.byteLength > 12 * 1024 * 1024) {
      return NextResponse.json({ detail: 'Upload exceeds the operator request limit.' }, { status: 413 });
    }
    headers.set('Content-Type', contentType);
  }

  const target = new URL(
    `${backendApiBaseUrl()}/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`,
  );
  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    });
    if (upstream.status === 401) await clearOperatorSessionCookie();

    const responseHeaders = new Headers({
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    });
    const responseContentType = upstream.headers.get('content-type');
    if (responseContentType) responseHeaders.set('Content-Type', responseContentType);
    return new NextResponse(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('Operator API proxy failed:', error);
    return NextResponse.json({ detail: 'Operator service is unavailable.' }, { status: 503 });
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, (await context.params).path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, (await context.params).path);
}
