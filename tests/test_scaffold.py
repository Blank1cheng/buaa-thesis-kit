from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_top_level_directories_exist():
    for rel in [
        "templates",
        "rules",
        "schemas",
        "scripts",
        "references",
        "buaa_thesis_kit",
        "tests",
    ]:
        assert (ROOT / rel).is_dir(), rel


def test_package_imports():
    import buaa_thesis_kit

    assert buaa_thesis_kit.__version__ == "0.1.0"
