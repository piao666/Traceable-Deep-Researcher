'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useResearchTask } from '@/hooks/useResearchTask';
import { markdownToHtml } from '@/helpers/markdownHelper';
import type { TaskStatus } from '@/types/research';
import '@/styles/markdown.css';

const statusNames:Record<TaskStatus,string>={queued:'等待执行',running:'正在研究',waiting_for_review:'等待审核',
  succeeded:'研究已完成',failed:'研究失败',cancel_requested:'正在停止',cancelled:'已停止',interrupted:'研究已中断'};
const formatNames:Record<string,string>={pdf:'便携文档',docx:'可编辑文档',md:'纯文本报告'};

export default function TaskPage({params}:{params:{id:string}}) {
  const {task,projection,error,cancel,resume,refresh}=useResearchTask(params.id);
  const [html,setHtml]=useState('');
  const [actionError,setActionError]=useState('');
  const body=task?.result?.report_markdown || projection.draft;
  useEffect(()=>{if(task?.status==='succeeded')window.dispatchEvent(new Event('tdr:history-changed'));},[task?.status]);
  useEffect(()=>{
    let active=true;
    void markdownToHtml(body).then(value=>{if(active)setHtml(value);});
    return ()=>{active=false;};
  },[body]);
  const act=async (action:()=>Promise<void>)=>{
    setActionError('');try{await action();}catch(cause){setActionError(cause instanceof Error ? cause.message : '操作失败，请重试。');}
  };
  return <main className="mx-auto w-full max-w-5xl px-4 py-6 text-gray-100 sm:px-8">
    <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
      <Link href="/" className="text-lg font-semibold text-teal-300">Traceable Deep Researcher</Link>
      <Link href="/" className="rounded-md border border-gray-700 px-4 py-2">新建研究</Link>
    </header>
    <section className="mb-6 rounded-xl border border-gray-800 bg-gray-900 p-5">
      <h1 className="mb-3 break-words text-xl font-semibold">{task?.request.task || '正在读取研究任务……'}</h1>
      <p role="status" className="text-teal-300">{task ? statusNames[task.status] : '正在连接研究服务……'}</p>
      <p className="mt-2 text-sm text-gray-400">任务已保存到服务器，可以关闭页面，之后使用当前地址继续查看。</p>
      {(error || actionError || task?.error) && <p role="alert" className="mt-3 text-amber-300">{actionError || error || task?.error?.message}</p>}
      <div className="mt-4 flex flex-wrap gap-3">
        {task && ['queued','running','cancel_requested'].includes(task.status) && <button className="rounded-md bg-gray-700 px-4 py-2" disabled={task.status==='cancel_requested'} onClick={()=>void act(cancel)}>停止研究</button>}
        {task && ['failed','interrupted'].includes(task.status) && <button className="rounded-md bg-teal-700 px-4 py-2" onClick={()=>void act(resume)}>恢复研究</button>}
        {task?.status==='succeeded' && <Link className="rounded-md bg-teal-700 px-4 py-2" href={'/research/'+params.id}>查看历史与继续提问</Link>}
      </div>
      {task && ['failed','interrupted'].includes(task.status) && <p className="mt-3 text-sm text-gray-400">恢复会复用兼容的已完成阶段；未完成部分可能重复调用模型或工具并产生费用。</p>}
    </section>
    {projection.messages.length>0 && <details className="mb-6 rounded-xl border border-gray-800 p-5"><summary className="cursor-pointer font-semibold">研究进展</summary><div className="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm text-gray-400">{projection.messages.map((message,index)=><p key={index} className="whitespace-pre-wrap break-words">{message}</p>)}</div></details>}
    {body && <article className="rounded-xl border border-gray-800 bg-gray-900 p-5 sm:p-8">
      <h2 className="mb-5 text-lg font-semibold">{task?.result ? '研究报告' : '报告草稿'}</h2>
      <div className="markdown-content prose prose-invert max-w-none" dangerouslySetInnerHTML={{__html:html}} />
    </article>}
    {task?.result && <section className="mt-6 rounded-xl border border-gray-800 p-5">
      <h2 className="mb-3 font-semibold">报告下载</h2>
      {(!task.exports || task.exports.length===0) && <p className="text-sm text-gray-400">正文已保存，下载文件正在准备。</p>}
      <div className="flex flex-wrap gap-3">{task.exports?.map(job=><div key={job.format} className="rounded-md bg-gray-800 px-4 py-3">
        <span>{formatNames[job.format] || '报告文件'}</span>
        {job.status==='succeeded' && job.path && <a className="ml-3 text-teal-300" href={'/'+job.path.replace(/^\/+/, '')} target="_blank" rel="noopener noreferrer">下载</a>}
        {['queued','running'].includes(job.status) && <span className="ml-3 text-gray-400">正在生成</span>}
        {job.status==='failed' && <button className="ml-3 text-amber-300" onClick={()=>void act(async()=>{
          const response=await fetch(`/api/research/${params.id}/exports/${job.format}/retry`,{method:'POST'});
          if(!response.ok)throw new Error('导出重试未成功，请稍后再试。');refresh();
        })}>重试导出</button>}
      </div>)}</div>
    </section>}
  </main>;
}
