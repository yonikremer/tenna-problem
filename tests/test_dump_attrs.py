import json
from pathlib import Path

from analysis import dump_attrs
import numpy as np


def test_jsonable_handles_scalars_and_arrays():
    assert dump_attrs.jsonable(3) == 3
    assert dump_attrs.jsonable("text") == "text"
    assert dump_attrs.jsonable(None) is None
    assert dump_attrs.jsonable(np.array([1, 2])) == [1, 2]
    fallback = dump_attrs.jsonable(object())
    assert isinstance(fallback, str)
    assert fallback.startswith("<object object at")


def test_dump_lists_attributes_and_variables(synthetic):
    data = dump_attrs.dump(synthetic.recording)
    assert data["file"] == synthetic.recording
    assert data["dimensions"]["sample"] == 32736
    assert set(data["variables"]) == {"i", "q"}
    assert data["variables"]["i"]["dtype"] == "float32"
    assert data["variables"]["q"]["shape"] == [32736]
    assert data["global_attributes"]["sample_rate_hz"] == 4_092_000.0
    assert data["global_attributes"]["target_cn0_dbhz_per_prn"] > 0


def test_main_writes_json(synthetic, capsys):
    dump_attrs.main([synthetic.recording])
    output = capsys.readouterr().out
    destination = Path(synthetic.recording).with_name("synthetic_l1_attrs.json")
    assert destination.exists()
    assert output.startswith(synthetic.recording)
    with open(destination, encoding="utf-8") as handle:
        written = json.load(handle)
    assert written["variables"]["i"]["shape"] == [32736]
    assert written["global_attributes"]["nominal_chip_rate_hz"] == 1_023_000.0
