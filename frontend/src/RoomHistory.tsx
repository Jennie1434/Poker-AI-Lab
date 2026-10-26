import {useEffect, useState} from 'react';
import {Entry, money, streetName} from './types';
import {PlayingCard} from './Table';
import {t} from './i18n';

type SeatStats={hands:number;net_chips:number;won_chips:number;lost_chips:number;biggest_win:number;biggest_loss:number;bb_per_100:number|null;won_rate:number;vpip_rate:number;pfr_rate:number;showdowns_rate:number};
type HandSummary={number:number;board:string[];pot:number;players:{id:string;position:string;cards:string[];payoff:number|null}[];actions:{player:string;street:string;kind:string;label:string;to:number;pay:number;all_in:boolean}[]};
export type RoomHistoryData={stats:Record<string,SeatStats>;hands:HandSummary[];completed_hands:number};

const percent=(value:number)=>`${Math.round(value*100)}%`;

// Fetched only when a hand completes; the owner's view never contains unshown opponent cards.
export function RoomHistory({load,handsPlayed,entries,hero,mode}:{load:()=>Promise<RoomHistoryData>;handsPlayed:number;entries:Entry[];hero:string;mode:string}){
    const [data,setData]=useState<RoomHistoryData|null>(null),[error,setError]=useState('');
    useEffect(()=>{let active=true;load().then(d=>{if(active)setData(d);}).catch(e=>{if(active)setError((e as Error).message);});return()=>{active=false;};},[handsPlayed]);
    const name=(id:string)=>id===hero?t('我'):entries.find(e=>e.id===id)?.name||id;
    if(error)return <p className="notice error" role="alert">{t(error)}</p>;
    if(!data||!data.completed_hands)return null;
    return <section className="room-hand-history" aria-label={t('手牌历史与统计')}>
      <h3>{t('统计')} · {t('已完成 {0} 手',data.completed_hands)}</h3>
      <div className="scroll-table"><table><thead><tr><th>{t('参赛席位')}</th><th>{t('手数')}</th><th>{t('净盈利')}</th><th>{t('赢得 / 输掉')}</th><th>{t('最大单手')}</th><th>bb/100</th><th>{t('赢下的手牌')}</th><th>VPIP</th><th>PFR</th><th>{t('摊牌')}</th></tr></thead>
      <tbody>{Object.entries(data.stats).map(([id,s])=><tr key={id}><td>{name(id)}</td><td>{s.hands}</td><td className={s.net_chips>=0?'positive':'negative'}>{money(s.net_chips,mode)}</td><td>+{money(s.won_chips,mode)} / −{money(s.lost_chips,mode)}</td><td>+{money(s.biggest_win,mode)} / {money(s.biggest_loss,mode)}</td><td>{s.bb_per_100===null?'—':s.bb_per_100.toFixed(1)}</td><td>{percent(s.won_rate)}</td><td>{percent(s.vpip_rate)}</td><td>{percent(s.pfr_rate)}</td><td>{percent(s.showdowns_rate)}</td></tr>)}</tbody></table></div>
      <p className="fine">{t('样本较小时统计波动很大；bb/100 为每 100 手赢得的大盲数。')}</p>
      <h3>{t('最近的手牌')}</h3>
      <div className="hand-history-list">{data.hands.map(h=>{const me=h.players.find(p=>p.id===hero);return <details key={h.number}>
        <summary><span>{t('第 {0} 手',h.number)}</span><span className="history-cards">{me?.cards.map((c,i)=><PlayingCard key={i} value={c} small/>)}</span><span className="history-cards">{h.board.map((c,i)=><PlayingCard key={i} value={c} small/>)}</span><strong className={(me?.payoff||0)>=0?'positive':'negative'}>{(me?.payoff||0)>0?'+':''}{money(me?.payoff||0,mode)}</strong></summary>
        <div className="hand-history-detail">{h.players.filter(p=>p.id!==hero).map(p=><p key={p.id}><span>{name(p.id)} · {p.position}</span><span className="history-cards">{p.cards.map((c,i)=><PlayingCard key={i} value={c} small/>)}</span><span>{(p.payoff||0)>0?'+':''}{money(p.payoff||0,mode)}</span></p>)}
        <ol>{h.actions.map((a,i)=><li key={i}><span>{t(streetName[a.street]||a.street)}</span> <strong>{name(a.player)}</strong> {t(a.label)}{a.kind==='raise'?' → '+money(a.to,mode):a.kind==='call'&&a.pay?' '+money(a.pay,mode):''}</li>)}</ol></div>
      </details>;})}</div>
    </section>;
}
