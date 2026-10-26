import {useEffect, useState} from 'react';
import {Eye, FastForward, Pause, Play, SkipForward} from 'lucide-react';
import {api, Entry, GameEvent, money} from './types';
import {PokerTable, actionText} from './Table';
import {t} from './i18n';
import {useRoomPlayback} from './useRoomPlayback';
import {PersonalAccess, usePersonalAccess} from './PersonalAccess';

type SeatStats={hands:number;net_chips:number;won:number;bb_per_100:number|null};
type Session={id:string;agents:Record<string,string>;names:Record<string,string>;hands_played:number;max_hands:number;stats:Record<string,SeatStats>};
type HandData={hand:{number:number;events:GameEvent[];payoffs:Record<string,number>};session:Session};
const COLORS:Record<string,string>={a:'#2f7d6d',b:'#9a753a'};

export function Spectate(){
    const access=usePersonalAccess();
    return <><PersonalAccess access={access}/>{access.user&&<Exhibition key={access.user.id}/>}</>;
}

function Exhibition(){
    const [agents,setAgents]=useState<{id:string;name:string}[]>([]);
    const [a,setA]=useState('cfr-v1'),[b,setB]=useState('tag');
    const [session,setSession]=useState<Session|null>(null),[hand,setHand]=useState<HandData['hand']|null>(null);
    const [auto,setAuto]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
    useEffect(()=>{api<{id:string;name:string}[]>('/api/spectate/agents').then(setAgents).catch(e=>setError(e.message));},[]);
    const load=async(id:string,number:number)=>{
        setBusy(true);setError('');
        try{const data=await api<HandData>(`/api/spectate/${id}/hands/${number}`);setHand(data.hand);setSession(data.session);}
        catch(e){setError((e as Error).message);setAuto(false);}finally{setBusy(false);}
    };
    const start=async()=>{
        setBusy(true);setError('');setHand(null);
        try{const created=await api<Session>('/api/spectate','POST',{agent_a:a,agent_b:b});setSession(created);setAuto(true);setBusy(false);await load(created.id,1);}
        catch(e){setError((e as Error).message);setBusy(false);}
    };
    const playback=useRoomPlayback(session?`spectate-${session.id}`:'',hand?.events||[],true);
    const events=playback.events,event=events.at(-1),state=event?.snapshot;
    const finished=!!hand&&!playback.behind;
    // Statistics include the hand being shown only once its playback ends: no spoilers.
    const [shown,setShown]=useState<Session['stats']|null>(null);
    useEffect(()=>{if(finished&&session)setShown(session.stats);},[finished,session]);
    useEffect(()=>{setShown(null);},[session?.id]);
    const canNext=!!session&&finished&&!busy&&session.hands_played<session.max_hands;
    // Deal the next hand a moment after the current one has been shown.
    useEffect(()=>{if(!auto||!canNext||!session)return;const timer=setTimeout(()=>void load(session.id,session.hands_played+1),1500);return()=>clearTimeout(timer);},[auto,canNext,session?.id,session?.hands_played]);
    const entries:Entry[]=session?(['a','b'] as const).map(seat=>({id:seat,name:session.names[seat],color:COLORS[seat],provider:'spectator'})):[];
    const recent:Record<string,NonNullable<GameEvent['action']>>={};for(const e of events)if(e.action)recent[e.action.player]=e.action;
    return <section className="rooms-page spectate-page">
      <div className="page-heading"><div><p className="eyebrow">{t('AI VS AI · LIVE')}</p><h1>{t('观战')}</h1><p className="muted">{t('选择两个智能体，逐手观看它们对局。两人桌现金局，每手 200 BB，按钮轮流；每个智能体只看到自己的底牌，观众可以看到双方底牌。')}</p></div></div>
      {error&&<p className="notice error" role="alert">{t(error)}</p>}
      <form className="spectate-setup" onSubmit={e=>{e.preventDefault();void start();}}>
        <label>{t('智能体 A')}<select aria-label={t('智能体 A')} value={a} onChange={e=>setA(e.target.value)}>{agents.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <span className="versus">VS</span>
        <label>{t('智能体 B')}<select aria-label={t('智能体 B')} value={b} onChange={e=>setB(e.target.value)}>{agents.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <button type="submit" className="primary" disabled={busy||!agents.length}><Eye size={16}/>{t(session?'重新开始观战':'开始观战')}</button>
      </form>
      {session&&<>
        <div className="run-toolbar"><div><h2>{session.names.a} vs {session.names.b}</h2><p className="fine">{t('第 {0} 手',hand?.number||1)} · {t('观战记录只保存在服务器内存中，不进入正式榜单。')}</p></div>
          <div className="inline-controls">
            <button className="secondary" onClick={()=>setAuto(v=>!v)} aria-pressed={!auto}>{auto?<Pause size={15}/>:<Play size={15}/>}<span>{t(auto?'暂停自动发牌':'继续自动发牌')}</span></button>
            <button className={playback.fast?'primary':'secondary'} aria-pressed={playback.fast} onClick={playback.toggle}><FastForward size={15}/><span>{t(playback.fast?'恢复正常速度':'快进')}</span></button>
            <button className="secondary" disabled={!canNext} onClick={()=>void load(session.id,session.hands_played+1)}><SkipForward size={15}/><span>{t('下一手')}</span></button>
          </div></div>
        {state?<><div className="room-current-action" aria-live="polite"><strong>{event?.action?session.names[event.action.player]:t('牌桌事件')}</strong><span>{event?.action?actionText(event.action,'cash'):t(event?.label||'')}</span></div>
          <div className="table-stage room-table"><PokerTable soundScope={`spectate-${session.id}`} state={state} entries={entries} mode="cash" event={event} recentActions={recent}/></div></>:<div className="empty-state">{t('正在发牌…')}</div>}
        <div className="scroll-table room-standings"><table><thead><tr><th>{t('智能体')}</th><th>{t('手数')}</th><th>{t('净盈利')}</th><th>bb/100</th><th>{t('赢下的手牌')}</th></tr></thead>
          <tbody>{(['a','b'] as const).map(seat=>{const s=shown?.[seat]||{hands:0,net_chips:0,won:0,bb_per_100:null};return <tr key={seat}><td>{session.names[seat]}</td><td>{s.hands}</td><td className={s.net_chips>=0?'positive':'negative'}>{money(s.net_chips)}</td><td>{s.bb_per_100===null?'—':s.bb_per_100.toFixed(1)}</td><td>{s.hands?Math.round(100*s.won/s.hands)+'%':'—'}</td></tr>;})}</tbody></table></div>
        <p className="fine">{t('样本较小时统计波动很大；bb/100 为每 100 手赢得的大盲数。')}</p>
        <div className="room-history"><h3>{t('本手行动记录')}</h3>{events.filter(e=>e.action||e.type==='board'||e.type==='settlement').slice().reverse().map(e=><p key={e.index}><span>{e.action?session.names[e.action.player]:t('牌桌事件')}</span><strong>{e.action?actionText(e.action,'cash'):t(e.label)}</strong></p>)}</div>
      </>}
    </section>;
}
