import weft


def test_package_importable():
    assert weft.__version__ == "0.1.0"


def test_specmodule_dependency_importable():
    import module_harness

    from llm.client import LLMResponse

    assert hasattr(module_harness, "call_harness")
    assert hasattr(module_harness, "Module")
    assert LLMResponse is not None
