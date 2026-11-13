import { NextResponse } from 'next/server';
import boundaries from '../../../../public/data/mumbai-wards.geojson';

export const dynamic = 'force-static';

export function GET() {
  return NextResponse.json(boundaries, {
    headers: {
      'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
    },
  });
}
