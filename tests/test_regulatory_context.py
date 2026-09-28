import json
import app as module
from regulatory_context import REGULATORY_CONTEXT


def test_deal_prompt_carries_dated_primary_sources(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key-not-real')
    monkeypatch.setattr(module, 'get_benchmark_for_postcode', lambda *args: None)
    prompts = []
    def complete(**kwargs):
        prompts.append(kwargs['messages'][0]['content'])
        return {'content': json.dumps({'verdict': 'Test analysis'})}
    monkeypatch.setattr(module.ai_gateway, 'complete', complete)
    module.get_ai_property_analysis(
        {'dealType': 'BTL', 'postcode': 'M14 5AA', 'purchasePrice': 200000},
        {'gross_yield': 6, 'monthly_cashflow': 150, 'deal_score': 44, 'article_4': {'known': False}},
    )
    assert len(prompts) == 1
    assert REGULATORY_CONTEXT in prompts[0]
    assert '1 May 2026' in prompts[0]
    assert 'by 2030' in prompts[0]


def test_btl_area_template_does_not_reintroduce_stale_timeline():
    template = str(module._area_section_template('BTL'))
    assert '2028 target' not in template
    assert 'Renters Reform Bill' not in template
    assert 'supplied regulatory context' in template
