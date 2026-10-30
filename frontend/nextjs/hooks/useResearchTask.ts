'use client';

import { useEffect, useRef, useState } from 'react';
import { applyTaskEvent, emptyProjection, TaskProjection } from '@/utils/taskEvents';
import type { ResearchTaskRequest, ResearchResult, TaskEvent, TaskStatus, ReviewStatus } from '@/types/research';

export interface ResearchTask {
  research_id:string; status:TaskStatus; review_status:ReviewStatus;
  request:ResearchTaskRequest; result:ResearchResult | null; last_seq:number;
  error:{code:string;message:string} | null;
  exports:{format:string;status:string;path?:string;error?:string}[];
}

export function useResearchTask(id:string) {
  const [task,setTask] = useState<ResearchTask | null>(null);
  const [projection,setProjection] = useState<TaskProjection>(emptyProjection);
  const [error,setError] = useState('');
  const [refresh,setRefresh] = useState(0);
  const stopped = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let current = emptyProjection();
    let timer: ReturnType<typeof setTimeout>;
    stopped.current = false;
    setTask(null); setError('');
    try {
      const stored = JSON.parse(sessionStorage.getItem('tdr.task.'+id) || 'null');
      if (stored && Number.isInteger(stored.lastSeq) && stored.lastSeq>=0 && typeof stored.draft==='string' && Array.isArray(stored.messages)) current=stored;
    } catch { /* A corrupt cache falls back to the durable event stream. */ }
    setProjection(current);

    const poll = async () => {
      try {
        const response = await fetch('/api/research/'+encodeURIComponent(id), {cache:'no-store',signal:controller.signal});
        if (!response.ok) throw new Error(response.status===404 ? '研究任务不存在。' : '暂时无法读取研究状态，正在重试……');
        let latest:ResearchTask = await response.json();
        if (current.lastSeq>latest.last_seq) current=emptyProjection();
        const eventsResponse = await fetch(`/api/research/${encodeURIComponent(id)}/events?after_seq=${current.lastSeq}&limit=100`, {cache:'no-store',signal:controller.signal});
        if (!eventsResponse.ok) throw new Error('暂时无法同步研究进度，正在重试……');
        const page:{events:TaskEvent[];resync_required?:boolean;snapshot?:ResearchTask & {projection:{draft:string;attempt_id:string | null}}} = await eventsResponse.json();
        const {events}=page;
        if(page.resync_required && page.snapshot){
          latest=page.snapshot;
          current={lastSeq:page.snapshot.last_seq,attemptId:page.snapshot.projection.attempt_id,
            draft:page.snapshot.result?.report_markdown || page.snapshot.projection.draft,messages:[]};
        }
        for (const event of events) {
          if (event.research_id!==id) throw new Error('研究进度标识不匹配。');
          current=applyTaskEvent(current,event);
        }
        if (controller.signal.aborted) return;
        setTask(latest);setProjection({...current});setError('');
        const serialized=JSON.stringify(current);
        try { sessionStorage.setItem('tdr.task.'+id,serialized.length<500000 ? serialized : JSON.stringify(emptyProjection())); } catch { /* Replaying after refresh remains available. */ }
        const terminal=['succeeded','failed','cancelled','interrupted'].includes(latest.status);
        // Poll completed tasks too while their independent export jobs are active.
        const exporting=latest.exports?.some(job=>['queued','running'].includes(job.status));
        if (!terminal || current.lastSeq<latest.last_seq || exporting) timer=setTimeout(poll,events.length===100 ? 0 : 600);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : '同步失败，正在重试……');
        timer=setTimeout(poll,1500);
      }
    };
    void poll();
    return () => { stopped.current=true;controller.abort();clearTimeout(timer); };
  },[id,refresh]);

  const command = async (action:'cancel'|'resume') => {
    const response=await fetch(`/api/research/${encodeURIComponent(id)}/${action}`,{method:'POST',cache:'no-store'});
    if (!response.ok) {
      const data=await response.json();
      throw new Error(typeof data.detail==='string' ? data.detail : '操作未完成，请刷新后重试。');
    }
    setRefresh(value=>value+1);
  };
  return {task,projection,error,cancel:()=>command('cancel'),resume:()=>command('resume'),refresh:()=>setRefresh(value=>value+1)};
}
