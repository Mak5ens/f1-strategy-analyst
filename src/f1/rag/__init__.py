"""Questions on the FIA rules: the production retrieval pipeline of `core`, with the profile of the FIA corpus."""

from core.gateway import gateway_client
from core.retrieval.embeddings import GatewayEmbedder
from core.retrieval.pipeline import PipelineConfig, RetrievalPipeline
from core.retrieval.rerank import GatewayReranker
from core.tracing import tracer
from f1.corpus import fia_index
from f1.rag.profile import FiaProfile

# The gateway's metrics count this app's spend apart from the agent's and the jobs' (`user` of each call).
END_USER = "f1-rag"


def rag_pipeline(config: PipelineConfig | None = None) -> RetrievalPipeline:
    """The pipeline over the FIA index, its models behind the gateway, traced to the f1 team's Langfuse project."""
    llm = gateway_client(end_user=END_USER)
    index = fia_index(GatewayEmbedder(llm))
    seasons = [int(season) for season in index.values("season")]
    profile = FiaProfile(seasons, [str(name) for name in index.values("grand_prix")])
    return RetrievalPipeline(
        index,
        profile,
        llm=llm,
        reranker=GatewayReranker(llm),
        tracer=tracer(),
        config=config,
    )
