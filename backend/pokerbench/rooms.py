"""Human tables use registry models, the same poker rules, and a private seat token."""
import hashlib
import secrets
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from .config import Entry, RunConfig
from .engine import observer_record


class CustomAgent(BaseModel):
    id: str = Field(pattern=r"^custom-[a-z0-9_-]{1,32}$")
    name: str = Field(min_length=1,max_length=60)
    endpoint: str = Field(min_length=1,max_length=2048)
    model: str = Field(min_length=1,max_length=160)
    api_format: Literal['chat_completions','responses','anthropic'] = 'chat_completions'

    @model_validator(mode='after')
    def endpoint_url(self):
        from .custom_protocol import agent_endpoint
        self.endpoint=agent_endpoint(self.endpoint,self.api_format)
        if not self.name.strip() or not self.model.strip():
            raise ValueError('Name and model cannot be blank.')
        return self

    def entry(self):
        return Entry(id=self.id,name=self.name,provider='openai_compatible',model=self.model,
            base_url=self.endpoint,key_env='',proxy=False,revision='user-supplied',credential_id=self.id,api_format=self.api_format,
            input_cny_per_million=0,output_cny_per_million=0)


class RoomInput(BaseModel):
    name: str = Field(default="My table",min_length=1,max_length=100)
    player_name: str = Field(default="You",min_length=1,max_length=40)
    mode: Literal["cash","sng"] = "cash"
    custom_agents: list[CustomAgent] = Field(default_factory=list,max_length=9)
    model_ids: list[str] = Field(min_length=1,max_length=9)
    billing_mode: Literal["hosted","personal"] = "hosted"
    deepseek_thinking: Literal["low","non-thinking"] = "low"
    max_hands: int = Field(default=5000,ge=1,le=100000)
    run_budget_cny: float = Field(default=20,gt=0,le=10000)


class HumanActionInput(BaseModel):
    hand_number: int = Field(ge=1)
    action_count: int = Field(ge=0)
    action_id: str = Field(max_length=80)


def selectable(entry):
    # These restrictions apply to human rooms; the benchmark roster stays intact.
    if entry.credential_id:return True
    identity=" ".join((entry.id,entry.name,entry.model,entry.expected_model or "")).lower()
    return entry.provider!="human" and not any(word in identity for word in ("gpt","luna"))


def create_room(runner, body, registry, *, owner_id=None):
    available={e.id:e for e in registry if selectable(e)}
    if any(pid not in available for pid in body.model_ids):
        raise ValueError("请选择列表中的模型，GPT 不参与自组局")
    entries=[available[pid].model_copy(deep=True) for pid in body.model_ids]
    cfr=any(e.provider=="local_cfr" for e in entries)
    if cfr and (len(entries)!=1 or body.mode!="cash"):
        # The CFR abstraction is heads-up cash with 200 BB stacks only.
        raise ValueError("CFR 对手仅支持一对一现金桌：请只选择一个 CFR 席位")
    if any(not runner.provider.available(e) and not (body.billing_mode=="personal" and e.provider in ("jev","deepseek")) for e in entries):
        raise ValueError("所选模型尚未配置连接")
    counts={}
    for index,entry in enumerate(entries):
        original=entry.id
        counts[original]=counts.get(original,0)+1
        entry.id=f"opponent-{index+1}"
        if body.model_ids.count(original)>1:
            entry.name=f"{entry.name} #{counts[original]}"
        if entry.provider=="deepseek":
            entry.reasoning_effort=body.deepseek_thinking
    human_id="human-player"
    entries.insert(0,Entry(id=human_id,name=body.player_name,provider="human",model="human",
                           base_url="",key_env="",proxy=False,revision="manual",color="#d9af4e"))
    cfg=RunConfig(name=body.name,mode=body.mode,entries=entries,human_player_id=human_id,
                  seed=secrets.randbelow(2**63),max_hands=body.max_hands,run_budget_cny=body.run_budget_cny,billing_mode=body.billing_mode,
                  decision_timeout=15,max_output_tokens=32768,cash_reset_at=(40000 if cfr else 200000) if body.mode=='cash' else None)
    token=secrets.token_urlsafe(32)
    run=runner.create(cfg,persist=False)
    run["player_token_hash"]=hashlib.sha256(token.encode()).hexdigest()
    runner.store.save_run(run,owner_id=owner_id)
    return run,token


def check_owner(run, request):
    token=request.headers.get("x-player-token","")
    if not run["config"].get("human_player_id") or not secrets.compare_digest(
        run.get("player_token_hash",""),hashlib.sha256(token.encode()).hexdigest()
    ):
        raise HTTPException(403,"此浏览器没有该真人席位的操作权限")


def room_record(record, hero=None):
    result=observer_record(record,hero=hero)
    result["analysis"]=None
    for event in result["events"]:
        if event.get("action"):
            event["action"].pop("decision",None)
    return result


def room_state(run, store):
    number=run["active_hand"] or run["hands_played"]
    if not number:
        return {"record":None,"action_count":0,"can_act":False}
    record=store.hand(run["id"],number)
    return {"record":room_record(record,run["config"]["human_player_id"]),
            "action_count":len(record["actions"]),"can_act":run["status"]=="waiting_human"}


def room_history(run, store, limit=30):
    """Completed-hand summaries and per-seat statistics for the room owner.

    Built from the owner's filtered view: opponents' cards appear only when
    they were shown at showdown; agent decisions are never included.
    """
    hero=run["config"]["human_player_id"]
    big_blind=run["config"].get("cash_big_blind",100) if run["config"].get("mode")=="cash" else None
    stats={}
    hands=[]
    for record in store.hands(run["id"]):
        if not record["complete"]:
            continue
        view=room_record(record,hero)
        final=view["events"][-1]["snapshot"]
        seats=[s for s in final["seats"] if s["position"]!="OUT"]
        live=[s for s in seats if not s["folded"]]
        actions=record["actions"]
        for seat in seats:
            row=stats.setdefault(seat["id"],{"hands":0,"net_chips":0,"won_chips":0,"lost_chips":0,"biggest_win":0,
                                             "biggest_loss":0,"won":0,"vpip":0,"pfr":0,"showdowns":0})
            payoff=seat["payoff"] or 0
            row["hands"]+=1
            row["net_chips"]+=payoff
            # Gross amounts explain a near-zero net after large swings.
            row["won_chips"]+=max(payoff,0)
            row["lost_chips"]+=max(-payoff,0)
            row["biggest_win"]=max(row["biggest_win"],payoff)
            row["biggest_loss"]=min(row["biggest_loss"],payoff)
            row["won"]+=(seat["payoff"] or 0)>0
            preflop=[a for a in actions if a["player"]==seat["id"] and a["street"]=="preflop"]
            row["vpip"]+=any(a["kind"] in ("call","raise") for a in preflop)
            row["pfr"]+=any(a["kind"]=="raise" for a in preflop)
            row["showdowns"]+=len(live)>1 and not seat["folded"]
        # "pot" is the largest pot shown during the hand (an uncalled all-in included);
        # "contested_pot" is what was actually at stake: twice the smaller commitment.
        hands.append({"number":final["hand_number"],"board":final["board"],
                      "pot":max(e["snapshot"]["pot"] for e in view["events"]),
                      "contested_pot":2*min(s["committed"] for s in seats),
                      "players":[{"id":s["id"],"position":s["position"],"cards":s["cards"],"payoff":s["payoff"]} for s in seats],
                      "actions":[{k:a[k] for k in ("player","street","kind","label","to","pay","all_in")} for a in actions]})
    for row in stats.values():
        hands_played=row["hands"]
        row["bb_per_100"]=row["net_chips"]/big_blind/hands_played*100 if big_blind and hands_played else None
        for key in ("won","vpip","pfr","showdowns"):
            row[f"{key}_rate"]=row[key]/hands_played if hands_played else 0
    return {"stats":stats,"hands":hands[::-1][:limit],"completed_hands":len(hands)}
