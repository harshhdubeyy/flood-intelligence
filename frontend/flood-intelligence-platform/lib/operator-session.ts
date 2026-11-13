import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';
import { cookies } from 'next/headers';

const COOKIE_NAME = 'fip_operator_session';
const SESSION_TTL_SECONDS = 4 * 60 * 60;

export type OperatorSession = {
  operatorId: string;
  token: string;
  expiresAt: number;
};

function sessionKey(): Buffer {
  const secret = process.env.OPERATOR_SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error('OPERATOR_SESSION_SECRET must contain at least 32 characters.');
  }
  return createHash('sha256').update(secret).digest();
}

export function backendApiBaseUrl(): string {
  const configuredUrl = process.env.BACKEND_API_URL ?? process.env.NEXT_PUBLIC_API_URL;
  if (!configuredUrl) throw new Error('BACKEND_API_URL is not configured.');

  const url = new URL(configuredUrl);
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('Backend API URL must use HTTP or HTTPS.');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('Backend API URL must not include credentials, query, or fragment.');
  }
  if (process.env.NODE_ENV === 'production' && url.protocol !== 'https:') {
    throw new Error('Production operator authentication requires an HTTPS backend URL.');
  }

  const pathname = url.pathname.replace(/\/+$/, '');
  url.pathname = pathname.endsWith('/v1') ? pathname : `${pathname}/v1`;
  return url.toString().replace(/\/+$/, '');
}

export function sealOperatorSession(session: OperatorSession): string {
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', sessionKey(), nonce);
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(session), 'utf8'),
    cipher.final(),
  ]);
  return [
    nonce.toString('base64url'),
    cipher.getAuthTag().toString('base64url'),
    ciphertext.toString('base64url'),
  ].join('.');
}

export function readOperatorSession(value: string | undefined): OperatorSession | null {
  if (!value) return null;
  try {
    const [nonceValue, tagValue, ciphertextValue] = value.split('.');
    if (!nonceValue || !tagValue || !ciphertextValue) return null;
    const decipher = createDecipheriv(
      'aes-256-gcm',
      sessionKey(),
      Buffer.from(nonceValue, 'base64url'),
    );
    decipher.setAuthTag(Buffer.from(tagValue, 'base64url'));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(ciphertextValue, 'base64url')),
      decipher.final(),
    ]).toString('utf8');
    const session = JSON.parse(plaintext) as OperatorSession;
    if (
      typeof session.operatorId !== 'string' ||
      typeof session.token !== 'string' ||
      typeof session.expiresAt !== 'number' ||
      session.expiresAt <= Date.now()
    ) {
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export async function setOperatorSessionCookie(value: string): Promise<void> {
  (await cookies()).set(COOKIE_NAME, value, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/api/operator',
    maxAge: SESSION_TTL_SECONDS,
  });
}

export async function clearOperatorSessionCookie(): Promise<void> {
  (await cookies()).set(COOKIE_NAME, '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/api/operator',
    maxAge: 0,
  });
}

export async function operatorSessionFromCookie(): Promise<OperatorSession | null> {
  return readOperatorSession((await cookies()).get(COOKIE_NAME)?.value);
}

export const operatorSessionTtlSeconds = SESSION_TTL_SECONDS;
