"""
The Resonance modular network.

Design principle
----------------
With only ~8,274 independent clusters of training data, an unconstrained network
would memorise. So the architecture is not free-form: every module, every
connection between modules, and the SIGN of several weights is fixed by
published findings. That inductive bias is simultaneously

  (a) the research alignment, and
  (b) the primary regulariser - it removes most of the hypothesis space before
      a single gradient step is taken.

Six modules, mapped to constructs that noninvasive methods can actually measure
(Pradeep K et al. 2026, F1000Research - attention, affective arousal, memory
encoding, valuation; plus approach motivation from frontal alpha asymmetry, plus
processing fluency):

  SALIENCE       attention capture            anterior insula / dorsal ACC
  AFFECT         affective arousal            amygdala
  VALUATION      subjective value             vmPFC / ventral striatum
  ENCODING       memory encoding              hippocampus / MTL
  APPROACH       approach-avoidance           L/R prefrontal asymmetry
  CONTROL        processing fluency / load    dlPFC

These are NOT claims to measure neural activity. Each module is a psychometric
score computed from human-rated norms, named for the system the literature
associates with that construct.

Hard-coded research constraints
-------------------------------
C1  Arousal -> outcome is INVERTED-U, not monotonic (Yerkes-Dodson).
    Implemented as an explicit quadratic whose leading coefficient is forced
    negative, so the optimum is interior and learned, but the shape cannot
    invert to a U no matter what the data says.

C2  Arousal ENHANCES memory encoding, multiplicatively and non-negatively
    (Cahill & McGaugh; emotional arousal aids consolidation).
    Gate is softplus-constrained >= 0.

C3  Attention GATES valuation - value cannot be assigned to what was never
    attended (Krajbich et al., attentional drift-diffusion).
    Multiplicative gate in [0,1] via sigmoid.

C4  Processing fluency -> positive evaluation is MONOTONIC INCREASING
    (Reber, Winkielman & Schwarz). Weight forced non-negative.

C5  Cognitive load -> outcome is MONOTONIC DECREASING. Weight forced
    non-positive.

Constraints are enforced by construction (reparameterisation), not by penalty,
so they hold exactly at every point in training rather than approximately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F

MODULES = ("salience", "affect", "valuation", "encoding", "approach", "control")


@dataclass
class ModelConfig:
    n_features: int = 50          # see pipeline/features.py FEATURE_NAMES
    # Deliberately tiny. At hidden=16 the parameter/independent-item ratio was
    # 0.88 against 5,791 training clusters, which capacity_report calls TIGHT.
    # Halving it brings the ratio to ~0.45 and buys real headroom against
    # memorisation; raise it only if learning curves show underfitting.
    module_hidden: int = 8
    n_audiences: int = 12         # demographic segments
    audience_dim: int = 4
    dropout: float = 0.3
    # Modules whose activation is bounded [0,1]; approach is signed [-1,1].
    signed: tuple[str, ...] = field(default_factory=lambda: ("approach",))


class ModuleHead(nn.Module):
    """One functional module: features -> a single interpretable activation.

    Kept to one small hidden layer. The bottleneck to a scalar is severe and
    intentional: everything the network knows must pass through six numbers a
    human can read, which sharply limits its ability to memorise individual ads.
    """

    def __init__(self, n_features: int, hidden: int, dropout: float,
                 signed: bool = False):
        super().__init__()
        self.signed = signed
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.LayerNorm(hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.net(x).squeeze(-1)
        return torch.tanh(z) if self.signed else torch.sigmoid(z)


class ResonanceNet(nn.Module):
    """Six modules, research-fixed interactions, audience conditioning."""

    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg

        self.modules_ = nn.ModuleDict({
            name: ModuleHead(cfg.n_features, cfg.module_hidden, cfg.dropout,
                             signed=name in cfg.signed)
            for name in MODULES
        })

        # Audience conditioning: a demographic segment scales module gains.
        # Multiplicative and centred on 1.0 so an unknown audience is a no-op.
        self.audience = nn.Embedding(cfg.n_audiences, cfg.audience_dim)
        self.audience_gain = nn.Linear(cfg.audience_dim, len(MODULES))
        nn.init.zeros_(self.audience_gain.weight)
        nn.init.zeros_(self.audience_gain.bias)

        # --- C2: arousal -> encoding, non-negative -----------------------
        self._arousal_to_encoding = nn.Parameter(torch.tensor(0.0))
        # --- C3: salience -> valuation gate ------------------------------
        self._salience_gate_w = nn.Parameter(torch.tensor(1.0))
        self._salience_gate_b = nn.Parameter(torch.tensor(0.0))
        # --- C1: inverted-U on arousal -----------------------------------
        self._arousal_quad = nn.Parameter(torch.tensor(0.5))   # -> negative
        self._arousal_lin = nn.Parameter(torch.tensor(0.0))
        # --- C4/C5: signed contributions ---------------------------------
        self._fluency_w = nn.Parameter(torch.tensor(0.1))      # -> >= 0
        self._load_w = nn.Parameter(torch.tensor(0.1))         # -> <= 0
        # Unconstrained contributions of the remaining modules.
        self.free_w = nn.Linear(3, 1)                          # sal, val, enc
        self.bias = nn.Parameter(torch.zeros(1))

    # -- constrained reparameterisations ----------------------------------
    @property
    def arousal_to_encoding(self) -> torch.Tensor:
        return F.softplus(self._arousal_to_encoding)           # C2: >= 0

    @property
    def arousal_quad(self) -> torch.Tensor:
        return -F.softplus(self._arousal_quad)                 # C1: <  0

    @property
    def fluency_w(self) -> torch.Tensor:
        return F.softplus(self._fluency_w)                     # C4: >= 0

    @property
    def load_w(self) -> torch.Tensor:
        return -F.softplus(self._load_w)                       # C5: <= 0

    def forward(self, x: torch.Tensor,
                audience: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        acts = {name: head(x) for name, head in self.modules_.items()}

        if audience is not None:
            gains = 1.0 + torch.tanh(self.audience_gain(self.audience(audience)))
            for i, name in enumerate(MODULES):
                acts[name] = acts[name] * gains[:, i]

        raw = dict(acts)

        # C3: attention gates valuation.
        gate = torch.sigmoid(self._salience_gate_w * acts["salience"]
                             + self._salience_gate_b)
        acts["valuation"] = acts["valuation"] * gate

        # C2: arousal enhances encoding.
        acts["encoding"] = acts["encoding"] * (
            1.0 + self.arousal_to_encoding * acts["affect"])

        # C1: inverted-U in arousal.
        a = acts["affect"]
        arousal_term = self.arousal_quad * a.pow(2) + self._arousal_lin * a

        # C4 / C5: monotone fluency (+) and cognitive load (-).
        fluency = acts["control"]
        control_term = self.fluency_w * fluency + self.load_w * (1.0 - fluency)

        free = self.free_w(torch.stack(
            [acts["salience"], acts["valuation"], acts["encoding"]], dim=-1)
        ).squeeze(-1)

        score = arousal_term + control_term + free + self.bias

        return {
            "score": score,
            "modules": acts,
            "modules_raw": raw,
            # diagnostic only - detached so callers can print it freely
            "arousal_optimum": self.arousal_optimum().detach(),
        }

    def arousal_optimum(self) -> torch.Tensor:
        """Vertex of the inverted-U - the arousal level the model considers ideal."""
        return (-self._arousal_lin / (2.0 * self.arousal_quad)).clamp(0.0, 1.0)

    # -- introspection -----------------------------------------------------
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def capacity_report(self, n_train_clusters: int) -> str:
        """Parameters per independent training item - the overfitting canary.

        Rule of thumb: comfortably below 1.0 is healthy; above ~1.0 the model
        has enough freedom to memorise the training set.
        """
        p = self.n_parameters()
        ratio = p / max(n_train_clusters, 1)
        verdict = ("OK" if ratio < 0.5 else
                   "TIGHT" if ratio < 1.0 else "OVERPARAMETERISED")
        return (f"parameters={p}  independent_train_items={n_train_clusters}  "
                f"ratio={ratio:.2f}  [{verdict}]")


def describe_constraints() -> str:
    return "\n".join([
        "C1 arousal->outcome inverted-U   (Yerkes-Dodson)      quad coef < 0",
        "C2 arousal->encoding enhancing   (Cahill & McGaugh)   gate >= 0",
        "C3 attention gates valuation     (Krajbich et al.)    gate in [0,1]",
        "C4 fluency->evaluation increasing(Reber et al.)       weight >= 0",
        "C5 cognitive load->outcome decr. (load literature)    weight <= 0",
    ])
