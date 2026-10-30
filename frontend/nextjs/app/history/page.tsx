'use client';

import Link from 'next/link';
import {useEffect,useState} from 'react';
import type {ResearchHistoryItem} from '@/types/data';

export default function HistoryPage(){
  const [page,setPage]=useState(0),[items,setItems]=useState<ResearchHistoryItem[]>([]);
  const [loading,setLoading]=useState(false),[message,setMessage]=useState(''),[refresh,setRefresh]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);
    void fetch(`/api/reports?limit=50&offset=${page*50}`,{cache:'no-store',signal:controller.signal})
      .then(async response=>{if(!response.ok)throw new Error('读取研究记录失败');const body=await response.json();setItems(body.reports || []);})
      .catch(error=>{if(!controller.signal.aborted)setMessage(error.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[page,refresh]);
  const importLocal=async()=>{
    setLoading(true);setMessage('正在检查本机旧记录……');
    try{
      const local=JSON.parse(localStorage.getItem('researchHistory') || '[]');
      if(!Array.isArray(local))throw new Error('本机记录格式无效');
      let count=0;
      for(const item of local){
        if(!item.id || !item.question || !item.answer || item.origin==='task')continue;
        const existing=await fetch('/api/reports/'+encodeURIComponent(item.id),{cache:'no-store'});
        if(existing.status!==404){if(!existing.ok)throw new Error('检查旧记录失败，请稍后重试。');continue;}
        const saved=await fetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
        if(!saved.ok)throw new Error('部分记录导入失败，可再次执行；已有记录不会重复导入。');count++;
      }
      setMessage(`已导入 ${count} 条旧记录；服务器已有记录保持不变。`);
      window.dispatchEvent(new Event('tdr:history-changed'));setRefresh(value=>value+1);
    }catch(error){setMessage(error instanceof Error ? error.message : '导入失败，请重试。');}
    finally{setLoading(false);}
  };
  return <main className="mx-auto w-full max-w-4xl px-4 py-8 text-gray-100">
    <header className="mb-8 flex flex-wrap items-center justify-between gap-4"><Link href="/" className="font-semibold text-teal-300">Traceable Deep Researcher</Link><Link href="/">新建研究</Link></header>
    <h1 className="mb-6 text-2xl font-semibold">研究记录</h1>
    <button disabled={loading} onClick={()=>void importLocal()} className="mb-4 rounded-md bg-gray-800 px-4 py-2">导入本机旧记录</button>
    {message && <p role="status" className="mb-4 text-amber-300">{message}</p>}
    {loading && <p>正在读取……</p>}
    {!loading && !items.length && <p className="text-gray-400">暂无研究记录</p>}
    <ul className="space-y-3">{items.map(item=><li key={item.id}><Link href={'/research/'+encodeURIComponent(item.id)} className="block rounded-lg border border-gray-800 bg-gray-900 p-4"><h2 className="break-words">{item.question || '未命名研究'}</h2><p className="mt-2 text-sm text-gray-400">{new Date(item.timestamp).toLocaleString('zh-CN')}</p></Link></li>)}</ul>
    <nav className="mt-6 flex items-center gap-4" aria-label="研究记录分页"><button disabled={page===0 || loading} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page+1} 页</span><button disabled={items.length<50 || loading} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>
  </main>;
}
