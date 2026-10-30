"""Non-secret execution configuration fingerprint, captured at submission."""

from hashlib import sha256
import os
from pathlib import Path

FIELDS=('FAST_LLM','SMART_LLM','STRATEGIC_LLM','RETRIEVER','LANGUAGE','CONFIG_PATH',
        'CONTEXT_FILTER','MAX_ITERATIONS','MAX_SEARCH_RESULTS_PER_QUERY','TOTAL_WORDS',
        'CURATE_SOURCES','IMAGE_GENERATION_ENABLED','DEEP_RESEARCH_BREADTH',
        'DEEP_RESEARCH_DEPTH','DEEP_RESEARCH_CONCURRENCY')


def configuration_snapshot():
    snapshot={key:os.getenv(key) for key in FIELDS}
    # Optional model kwargs can contain credentials; only keep a digest.
    snapshot['LLM_KWARGS_HASH']=sha256(os.getenv('LLM_KWARGS','').encode()).hexdigest()
    path=os.getenv('CONFIG_PATH','')
    if path and Path(path).is_file():
        snapshot['CONFIG_FILE_HASH']=sha256(Path(path).read_bytes()).hexdigest()
    return snapshot
