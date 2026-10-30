import pytest
from backend.server.tasks.result_adapter import normalize_result


@pytest.mark.parametrize('value', ['完整多代理正文', {'report':'完整多代理正文'}, ('完整多代理正文', None)])
def test_legacy_results_keep_entire_markdown(value):
    assert normalize_result(value).report_markdown == '完整多代理正文'


@pytest.mark.parametrize('value', ['', None, {'report':None}, 42])
def test_missing_report_is_not_success(value):
    with pytest.raises(ValueError):
        normalize_result(value)
