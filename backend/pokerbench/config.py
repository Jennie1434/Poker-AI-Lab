from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
BLINDS = [(50,100,0),(75,150,0),(100,200,200),(150,300,300),(200,400,400),
          (300,600,600),(400,800,800),(500,1000,1000),(600,1200,1200),
          (800,1600,1600),(1000,2000,2000),(1500,3000,3000),(2000,4000,4000),
          (3000,6000,6000),(4000,8000,8000)]
ROSTER = [
    ("jev", "Jev", "#176b54"), ("semif", "SemIf", "#487dc0"),
    ("nanojev", "NanoJev", "#c47b3b"), ("jevlike", "jevlike", "#9672ab"),
    ("kev", "kev", "#cb686d"), ("simple-jev", "simple-jev", "#4e9b9a"),
    ("openjev-sglang", "openjev-sglang", "#968546"),
    ("gemini", "Gemini 3.8 Flash", "#597aaf"),
    ("deepseek", "DeepSeek V4.1 Flash", "#4455ae"),
    ("luna", "GPT-5.6 Luna", "#6a7772"),
]


# TypeSafe's published Jev 1.14 rate: input billed, output currently free.
JEV_USD_PER_MILLION = (0.042, 0.0)
JEV_DEFAULTS = {"base_url": "https://api.typesafe.ai", "key_env": "JEV_API_KEY", "model": "jev-1.14.0"}
PRICE_FIELDS = {"input_cny_per_million", "output_cny_per_million", "input_usd_per_million", "output_usd_per_million"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    jev_api_key: str = ""
    pokerbench_budget_cny: float = 10000
    pokerbench_admin_token: str = ""
    pokerbench_invite_code: str = ""
    pokerbench_custom_proxy_url: str = ""
    pokerbench_data_dir: str = str(ROOT / "data")
    # CNY per USD for USD-priced entries (Jev). Reference default: mid-market 6.708 on
    # 2026-09-09 (currencybeacon.com), rounded up; set POKERBENCH_USD_CNY_RATE to update it.
    # 0 refuses every USD-priced call.
    pokerbench_usd_cny_rate: float = Field(default=6.71, ge=0)


class Entry(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    name: str
    color: str = "#176b54"
    provider: Literal["deepseek", "openai_compatible", "jev", "systemone", "human", "local_cfr"] = "deepseek"
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    key_env: str = "DEEPSEEK_API_KEY"
    structured_outputs: bool = False
    reasoning_effort: Literal["low", "non-thinking"] | None = None
    reasoning_parameter: Literal["reasoning_effort", "reasoning"] = "reasoning_effort"
    abstention_policy: Literal["reject", "condition_on_legal_actions"] = "reject"
    proxy: bool = True
    input_cny_per_million: float = Field(default=2.16, ge=0)
    output_cny_per_million: float = Field(default=8.64, ge=0)
    # Prices in the provider's own currency; when set they replace the CNY prices.
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)
    revision: str = "unconfigured"
    credential_id: str | None = None
    api_format: Literal['chat_completions', 'responses', 'anthropic'] = 'chat_completions'
    expected_model: str | None = None
    expected_revision: str | None = None

    @model_validator(mode="after")
    def reasoning_supported(self):
        if self.reasoning_effort=="non-thinking" and self.provider!="deepseek":
            raise ValueError("non-thinking 仅支持 DeepSeek")
        if self.reasoning_effort and self.provider not in ("deepseek","openai_compatible"):
            raise ValueError("reasoning_effort 仅用于官方 adapter 的聊天模型")
        return self

    @model_validator(mode="after")
    def official_jev_defaults(self):
        # A Jev entry must never inherit DeepSeek's endpoint, key or prices.
        if self.provider=="jev":
            for name,value in JEV_DEFAULTS.items():
                if name not in self.model_fields_set:
                    setattr(self,name,value)
            if not self.model_fields_set & PRICE_FIELDS:
                self.input_usd_per_million,self.output_usd_per_million=JEV_USD_PER_MILLION
        if (self.input_usd_per_million is None)!=(self.output_usd_per_million is None):
            raise ValueError("USD 价格需同时给出输入与输出")
        return self

    def prices_cny(self, usd_cny_rate: float) -> tuple[float, float]:
        """(input, output) CNY per million tokens; USD prices need a configured rate."""
        if self.input_usd_per_million is None:
            return self.input_cny_per_million,self.output_cny_per_million
        if not usd_cny_rate>0:
            raise ValueError("未配置 POKERBENCH_USD_CNY_RATE，无法换算 USD 计价模型的费用")
        return self.input_usd_per_million*usd_cny_rate,self.output_usd_per_million*usd_cny_rate


def default_entries() -> list[Entry]:
    return [Entry(id=i, name=n, color=c) for i, n, c in ROSTER]


class RunConfig(BaseModel):
    name: str = Field(default="十席端点测试", min_length=1, max_length=100)
    mode: Literal["cash", "sng"] = "cash"
    human_player_id: str | None = None
    billing_mode: Literal["hosted","personal"] = "hosted"
    max_hands: int = Field(default=10, ge=1, le=100000)
    seed: int = Field(default=20260920, ge=0, le=2**63-1)
    bankroll: int = Field(default=1000000, ge=1)  # cents, 10,000 virtual units
    buy_in: int = Field(default=20000, ge=1)
    cash_small_blind: int = Field(default=50, ge=1)
    cash_big_blind: int = Field(default=100, ge=1)
    settle_every: int = Field(default=500, ge=1)
    cash_reset_at: int | None = Field(default=None, gt=0)
    sng_starting_stack: int = Field(default=20000, ge=1)
    level_every: int = Field(default=200, ge=1)
    blind_levels: list[tuple[int, int, int]] = Field(default_factory=lambda: BLINDS.copy())
    shuffle_each_orbit: bool = True
    entries: list[Entry] = Field(default_factory=default_entries, min_length=2, max_length=10)
    run_budget_cny: float = Field(default=20, gt=0, le=10000)
    decision_timeout: float = Field(default=120, ge=10, le=600)
    max_output_tokens: int = Field(default=8192, ge=1024, le=131072)

    @model_validator(mode="after")
    def consistent(self):
        humans=[e.id for e in self.entries if e.provider=="human"]
        if humans!=([self.human_player_id] if self.human_player_id else []):
            raise ValueError("自组局必须有且仅有一个匹配的真人席位")
        if self.buy_in > self.bankroll:
            raise ValueError("买入不能超过总资产")
        if self.cash_reset_at is not None and (self.cash_reset_at<=self.buy_in or self.cash_reset_at%50):
            raise ValueError("结码阈值必须大于买入且为 0.5 的整数倍")
        if self.cash_small_blind > self.cash_big_blind:
            raise ValueError("小盲不能大于大盲")
        if len({e.id for e in self.entries}) != len(self.entries):
            raise ValueError("参赛席位 ID 不可重复")
        if not self.blind_levels or any(sb < 1 or bb < sb or ante < 0 for sb,bb,ante in self.blind_levels):
            raise ValueError("盲注表无效")
        return self

    def blinds(self, completed_hands: int) -> tuple[int, int, int]:
        if self.mode == "cash":
            return self.cash_small_blind, self.cash_big_blind, 0
        # User asked for the supplied schedule only: hold its last level.
        return self.blind_levels[min(completed_hands // self.level_every, len(self.blind_levels)-1)]
