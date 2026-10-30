import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function proxy(request: Request, {params}: {params:{path?:string[]}}) {
  const parts = params.path || [];
  if (parts.some(part => !/^[a-zA-Z0-9_-]+$/.test(part))) {
    return NextResponse.json({detail:'无效的任务地址'}, {status:400});
  }
  const base = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_TDR_API_URL || 'http://localhost:8000';
  const url = new URL(request.url);
  const headers: Record<string,string> = {'Content-Type':'application/json'};
  const key = request.headers.get('Idempotency-Key');
  if (key) headers['Idempotency-Key'] = key;
  try {
    const response = await fetch(`${base}/api/research${parts.length ? '/'+parts.join('/') : ''}${url.search}`, {
      method:request.method, headers, cache:'no-store',
      body:request.method==='POST' ? await request.text() : undefined,
    });
    const responseHeaders:Record<string,string>={'Content-Type':response.headers.get('Content-Type') || 'application/json','Cache-Control':'no-store'};
    const disposition=response.headers.get('Content-Disposition');
    if(disposition)responseHeaders['Content-Disposition']=disposition;
    return new NextResponse(response.body, {status:response.status, headers:responseHeaders});
  } catch {
    return NextResponse.json({detail:'暂时无法连接研究服务，请稍后重试。'}, {status:502,headers:{'Cache-Control':'no-store'}});
  }
}

export const GET = proxy;
export const POST = proxy;
