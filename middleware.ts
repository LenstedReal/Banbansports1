import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const host = request.headers.get('host');

  // Yalnızca doğrudan banbansports.vercel.app adresinden gelen istekleri hefle
  if (host === 'banbansports.vercel.app') {
    const targetUrl = new URL(
      request.nextUrl.pathname + request.nextUrl.search,
      'https://banban.lenstedreal.xyz'
    );

    // Test aşamasında cache problemlerini önlemek için 307 (Geçici Yönlendirme) kullanıyoruz
    return NextResponse.redirect(targetUrl, 307);
  }

  return NextResponse.next();
}

export const config = {
  // FastAPI /api/* isteklerini Next.js middleware'inden geçirip
  // Vercel Python function routing'ine bırak.
  matcher: ['/((?!api(?:/|$)).*)'],
};
