"""Convert legacy runner values without truncating a multi-agent string."""

from traceable_deep_researcher.runtime.contracts import ResearchResult


def normalize_result(value, researcher=None):
    if isinstance(value, ResearchResult):
        result = value
    else:
        if isinstance(value, tuple):
            value, researcher = value
        if isinstance(value, dict):
            value = value.get('report')
        if not isinstance(value, str):
            raise ValueError('Research must return a Markdown string')
        urls = researcher.get_source_urls() if researcher else []
        result = ResearchResult(value,
            sources=[{'url':url} if isinstance(url,str) else url for url in urls],
            cost_summary={'research_costs':researcher.get_costs()} if researcher else {})
    if not result.report_markdown.strip():
        raise ValueError('Research returned an empty report')
    return result
