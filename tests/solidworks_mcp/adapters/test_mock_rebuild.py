"""Check that the mock exposes the same rebuild result contract as the real adapter."""

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_mock_rebuild_requires_model_and_succeeds_with_model() -> None:
    adapter = MockSolidWorksAdapter({"mock_connect_delay": 0, "mock_model_delay": 0})
    await adapter.connect()

    missing = await adapter.rebuild_model()
    assert not missing.is_success
    assert missing.error == "No active model"

    opened = await adapter.open_model("test.sldprt")
    assert opened.is_success
    before = adapter._operation_count

    rebuilt = await adapter.rebuild_model()
    assert rebuilt.is_success
    assert adapter._operation_count == before + 1
