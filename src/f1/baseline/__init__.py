"""The F1 baseline (LAB-147): `core.baseline.Baseline` on the FIA index, with the race tools and the lake.

The system prompt is `prompt.txt`, versioned with the code: a change of it shows in the diff and in the evaluation.
"""

from importlib.resources import files

from core.baseline import Baseline, BaselineConfig
from core.gateway import gateway_client
from core.retrieval.embeddings import GatewayEmbedder
from f1.corpus import fia_index
from f1.data import connect
from f1.rag.profile import FiaProfile
from f1.tools import RaceData, catalog

# The gateway counts the baseline's cost apart from the RAG's and the agent's (its metrics by end user).
END_USER = "f1-baseline"
PROMPT = files("f1.baseline").joinpath("prompt.txt").read_text()


def baseline(config: BaselineConfig | None = None) -> Baseline:
    llm = gateway_client(end_user=END_USER)
    index = fia_index(GatewayEmbedder(llm))
    profile = FiaProfile(
        [int(season) for season in index.values("season")], [str(name) for name in index.values("grand_prix")]
    )
    return Baseline(index, profile, llm=llm, tools=catalog(RaceData(connect())), instructions=PROMPT, config=config)
