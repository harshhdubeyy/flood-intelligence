import { NextRequest, NextResponse } from 'next/server';
import {
  backendApiBaseUrl,
  clearOperatorSessionCookie,
  operatorSessionFromCookie,
  operatorSessionTtlSeconds,
  sealOperatorSession,
  setOperatorSessionCookie,
} from '../../../../lib/operator-session';

export const runtime = 'nodejs';

export async function GET() {
  const session = await operatorSessionFromCookie();
  if (!session) {
    await clearOperatorSessionCookie();
    return NextResponse.json({ detail: 'No active operator session.' }, { status: 401 });
  }
  return NextResponse.json(
    { operator_id: session.operatorId, expires_at: new Date(session.expiresAt).toISOString() },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}

function isSameOrigin(request: NextRequest): boolean {
  return request.headers.get('origin') === request.nextUrl.origin &&
    (process.env.NODE_ENV !== 'production' || request.nextUrl.protocol === 'https:');
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: 'Cross-origin requests are not allowed.' }, { status: 403 });
  }

  let credentials: { operator_id?: unknown; token?: unknown };
  try {
    credentials = await request.json();
  } catch {
    return NextResponse.json({ detail: 'Invalid login request.' }, { status: 400 });
  }
  if (
    typeof credentials.operator_id !== 'string' ||
    !credentials.operator_id.trim() ||
    credentials.operator_id.length > 80 ||
    typeof credentials.token !== 'string' ||
    !credentials.token ||
    credentials.token.length > 2048
  ) {
    return NextResponse.json({ detail: 'Operator ID and token are required.' }, { status: 400 });
  }

  try {
    const headers = { Authorization: `Bearer ${credentials.token}` };
    const identityResponse = await fetch(
      `${backendApiBaseUrl()}/reports/operator/identity`,
      { headers, cache: 'no-store', signal: AbortSignal.timeout(10_000) },
    );
    if (!identityResponse.ok) {
      return NextResponse.json(
        { detail: identityResponse.status === 401 ? 'Invalid operator credentials.' : 'Operator authentication is unavailable.' },
        { status: identityResponse.status === 401 ? 401 : 502 },
      );
    }
    const identity = (await identityResponse.json()) as { operator_id?: unknown };
    if (
      typeof identity.operator_id !== 'string' ||
      identity.operator_id !== credentials.operator_id.trim()
    ) {
      return NextResponse.json({ detail: 'Operator ID does not match the token.' }, { status: 401 });
    }

    const expiresAt = Date.now() + operatorSessionTtlSeconds * 1000;
    await setOperatorSessionCookie(sealOperatorSession({
      operatorId: identity.operator_id,
      token: credentials.token,
      expiresAt,
    }));
    return NextResponse.json(
      { operator_id: identity.operator_id, expires_at: new Date(expiresAt).toISOString() },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch (error) {
    console.error('Operator session creation failed:', error);
    return NextResponse.json({ detail: 'Operator authentication is unavailable.' }, { status: 503 });
  }
}

export async function DELETE(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: 'Cross-origin requests are not allowed.' }, { status: 403 });
  }
  await clearOperatorSessionCookie();
  return new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
}
