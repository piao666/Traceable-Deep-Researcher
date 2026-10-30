import type { TaskEvent } from '@/types/research';

export interface TaskProjection {
  lastSeq: number;
  attemptId: string | null;
  draft: string;
  messages: string[];
}

export const emptyProjection = (): TaskProjection => ({lastSeq:0,attemptId:null,draft:'',messages:[]});

export function applyTaskEvent(state:TaskProjection, event:TaskEvent): TaskProjection {
  if (event.seq <= state.lastSeq) return state;
  if (event.seq !== state.lastSeq+1) throw new Error('研究进度序号不连续，正在重新同步。');
  let next = {...state,lastSeq:event.seq};
  if (event.type==='report.draft_reset') {
    return {...next, attemptId:event.attempt_id || null, draft:'', messages:[]};
  }
  if (state.attemptId && event.attempt_id && event.attempt_id !== state.attemptId) return next;
  const legacy = event.payload.legacy as Record<string,unknown> | undefined;
  if (legacy?.type==='report' && typeof legacy.output==='string') next.draft += legacy.output;
  if (legacy?.type==='report_complete' && typeof legacy.output==='string') next.draft = legacy.output;
  if (legacy?.type==='logs' && typeof legacy.output==='string') next.messages=[...next.messages.slice(-49),legacy.output];
  return next;
}
