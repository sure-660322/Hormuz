import json
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import LLMResult, ChatGeneration

from backend.app.services.agent.business_tools import record_envelope
from backend.app.services.agent.request_guard import new_state
from backend.app.services.agent.track_observation import MAX_OBSERVATION_BYTES
from backend.app.services.agent.model_usage import ModelUsageRecorder
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.app.services.agent.ship_tracks import ShipTrackResult, TrackFix
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call

START = datetime(2026, 2, 28, 14, tzinfo=timezone.utc)
END = datetime(2026, 2, 28, 15, tzinfo=timezone.utc)


def payload(count):
    return dict(status='ok', ship_id=360, ship_name='TEST', start_at=START.isoformat(),
                end_at=END.isoformat(), fix_count=count, coverage_start=START.isoformat(),
                coverage_end=START.isoformat(), truncated=False, limitations=[],
                fixes=[dict(recorded_at=START.isoformat(), longitude=56.1,
                            latitude=26.1, speed=10, course=90, nav_status='underway')] * count)


@pytest.mark.parametrize('count', [0, 2, 50000])
def test_bounded_observation_preserves_evidence(count):
    state = new_state(8, 60)
    data = payload(count)
    if not count:
        data['status'] = 'no_data'
    before = json.dumps(data, ensure_ascii=False)
    observed = record_envelope(state, 'get_ship_track', data)
    summary = json.loads(observed)
    assert 'fixes' not in summary
    assert summary['fix_count'] == count
    assert len(observed.encode()) <= MAX_OBSERVATION_BYTES
    assert len(state['results']['call_001']['fixes']) == count
    if count:
        assert summary['latest_fix'] == data['fixes'][-1]
    if count == 50000:
        assert len(observed) < len(before) / 100
    print(f'count={count} before_chars={len(before)} after_chars={len(observed)} before_bytes={len(before.encode())} after_bytes={len(observed.encode())}')


def test_error_and_long_text_bounded():
    state = new_state(8, 60)
    data = payload(2)
    data['ship_name'] = '船' * 100000
    data['limitations'] = ['限' * 100000] * 20
    observed = record_envelope(state, 'get_ship_track', data)
    assert len(observed.encode()) <= MAX_OBSERVATION_BYTES
    assert json.loads(observed)['limitations_omitted'] == 12
    error = json.loads(record_envelope(state, 'get_ship_track', dict(status='error', code='INVALID_TOOL_ARGS', message='缩小窗口')))
    assert error['code'] == 'INVALID_TOOL_ARGS'


@pytest.mark.parametrize('count', [2, 50000])
@pytest.mark.parametrize('question,kind', [('显示船 ID 360 的轨迹', 'ship_track'), ('定位船 ID 360', 'ship_position')])
def test_multiround_model_messages_and_map(monkeypatch, caplog, count, question, kind):
    import logging
    caplog.set_level(logging.INFO)
    from backend.app.services.agent import business_tools
    track = ShipTrackResult(status='ok', ship_id=360, ship_name='TEST', start_at=START,
                            end_at=END, fix_count=count, coverage_start=START, coverage_end=START,
                            fixes=[TrackFix(START, 56.1, 26.1, 10, 90, 'underway')] * count)
    monkeypatch.setattr(business_tools, 'get_ship_track', lambda *a, **kw: track)
    llm = ScriptedFakeLLM(script=[tool_call('get_ship_track', {'ship_id': 360}),
                                  tool_call('search_project_knowledge', {'query': '轨迹'}, 'second'),
                                  '已核实轨迹。'])
    result = run_lc_agent(None, question, closure_at=START, end_at=END, llm=llm, sql_enabled=False)
    assert len(llm.received) == 3
    for messages in llm.received[1:]:
        tool_messages = [m for m in messages if isinstance(m, ToolMessage) and m.name == 'get_ship_track']
        assert len(tool_messages) == 1
        assert 'fixes' not in json.loads(tool_messages[0].content)
    assert len(result['results']['call_001']['fixes']) == count
    assert result['map_actions'][0]['type'] == kind
    assert result['map_actions'][0]['ship_id'] == 360
    if kind == 'ship_position':
        assert result['map_actions'][0]['recorded_at'] == START.isoformat()
    summaries = [r.message for r in caplog.records if r.message.startswith('agent_request_usage ')]
    assert len(summaries) == 1
    assert json.loads(summaries[0].split(' ', 1)[1])['model_calls'] == 3
    assert json.loads(summaries[0].split(' ', 1)[1])['input_tokens'] is None


def completed(recorder, run_id, usage=None, raw=None):
    message = AIMessage(content='secret prompt should never be logged', usage_metadata=usage,
                        response_metadata={'token_usage': raw} if raw else {})
    recorder.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)


def test_usage_dedup_missing_and_cache(caplog):
    import logging
    caplog.set_level(logging.INFO)
    recorder = ModelUsageRecorder('fixture-request')
    first, second = uuid4(), uuid4()
    recorder.on_chat_model_start({}, [], run_id=first)
    usage = dict(input_tokens=120, output_tokens=30, total_tokens=150, input_token_details={'cache_read': 100})
    completed(recorder, first, usage)
    completed(recorder, first, usage)
    completed(recorder, second, raw=dict(prompt_tokens=80, completion_tokens=20, prompt_cache_hit_tokens=50, prompt_cache_miss_tokens=30))
    snapshot = recorder.snapshot()
    assert snapshot['model_calls'] == 2
    assert snapshot['input_tokens'] == 200
    assert snapshot['output_tokens'] == 50
    assert snapshot['cache_read_tokens'] == 150
    assert snapshot['cache_miss_tokens'] is None
    completed(recorder, uuid4())
    assert recorder.snapshot()['input_tokens'] is None
    assert recorder.snapshot()['usage_status'] == 'unavailable'
    recorder.log_summary()
    assert 'secret prompt' not in caplog.text
    assert 'fixture-request' in caplog.text


def test_failed_call_is_not_zero_usage():
    recorder = ModelUsageRecorder('failed')
    recorder.on_llm_error(RuntimeError('secret'), run_id=uuid4())
    assert recorder.snapshot()['model_calls'] == 1
    assert recorder.snapshot()['input_tokens'] is None
