import pytest

from app.shared.infrastructure.seed import seed_default_data


@pytest.mark.asyncio
async def test_default_seed_requires_explicit_opt_in():
    with pytest.raises(RuntimeError, match="ALLOW_DEFAULT_SEED=true"):
        await seed_default_data()
