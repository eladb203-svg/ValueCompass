"""Code stage K2, step 4: the extraction store (rows) rebuilds exactly the dictionaries the current CSV loaders produce."""
import pytest

from src.etl.extraction_store import CSV_FILES, load_rows, reg_from_rows, rows_from_reg
from src.providers.bank_facts import load_regulatory
from src.providers.insurance_facts import load_insurance_regulatory
from src.providers.realestate_facts import load_realestate_extracted

LOADERS = {"bank": load_regulatory, "insurance": load_insurance_regulatory, "realestate": load_realestate_extracted}


@pytest.mark.parametrize("engine", list(LOADERS))
def test_rows_rebuild_the_current_loader_output(engine):
    if not CSV_FILES[engine].exists():
        pytest.skip(f"{CSV_FILES[engine].name} not present")
    old = LOADERS[engine]()
    rows = load_rows(engine)
    assert set(rows) == set(old)
    n = 0
    for tk, rs in rows.items():
        n += len(rs)
        new = reg_from_rows(engine, rs, sum_quarters=True)
        assert new == old[tk], tk
        assert list(new) == list(old[tk]), tk                       # item order
        if engine == "realestate":
            assert all(list(new[i]) == list(old[tk][i]) for i in new), tk   # year order inside an item
    assert n > 100


@pytest.mark.parametrize("engine", list(LOADERS))
def test_reg_to_rows_to_reg_is_identity(engine):
    if not CSV_FILES[engine].exists():
        pytest.skip(f"{CSV_FILES[engine].name} not present")
    old = LOADERS[engine]()
    for tk, reg in old.items():
        rows = rows_from_reg(engine, tk, reg)
        assert reg_from_rows(engine, rows) == reg


def test_unapproved_rows_are_not_visible_to_the_engines():
    from dataclasses import replace
    rows = next(iter(load_rows("bank").values()))
    hidden = [replace(r, approval_status="pending") if i == 0 else r for i, r in enumerate(rows)]
    assert rows[0].item_key not in reg_from_rows("bank", hidden)
    assert rows[0].item_key in reg_from_rows("bank", rows)
