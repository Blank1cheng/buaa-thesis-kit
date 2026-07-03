from buaa_thesis_kit.latex_to_omml import latex_to_omml


def test_latex_to_omml_converts_safe_linear_subscript_equation():
    omml = latex_to_omml("x_k = F x_{k-1} + w_k")

    assert "<m:oMathPara" in omml
    assert "<m:sSub>" in omml
    assert "<m:t>x</m:t>" in omml
    assert "<m:t>k</m:t>" in omml
    assert "<m:t>k-1</m:t>" in omml
    assert "<m:t>=</m:t>" in omml


def test_latex_to_omml_converts_safe_subscript_superscript_equation():
    omml = latex_to_omml("x_k^2 = y")

    assert "<m:oMathPara" in omml
    assert "<m:sSubSup>" in omml
    assert "<m:t>x</m:t>" in omml
    assert "<m:t>k</m:t>" in omml
    assert "<m:t>2</m:t>" in omml


def test_latex_to_omml_converts_fraction_and_square_root_macros():
    omml = latex_to_omml(r"y = \frac{x_k}{\sqrt{n}}")

    assert "<m:oMathPara" in omml
    assert "<m:f>" in omml
    assert "<m:num>" in omml
    assert "<m:den>" in omml
    assert "<m:rad>" in omml
    assert "<m:sSub>" in omml
    assert "<m:t>n</m:t>" in omml


def test_latex_to_omml_converts_greek_macros():
    omml = latex_to_omml(r"\alpha = \beta + \gamma")

    assert "<m:oMathPara" in omml
    assert f"<m:t>{chr(0x03B1)}</m:t>" in omml
    assert f"<m:t>{chr(0x03B2)}</m:t>" in omml
    assert f"<m:t>{chr(0x03B3)}</m:t>" in omml


def test_latex_to_omml_converts_sum_with_limits():
    omml = latex_to_omml(r"x = \sum_{i=1}^{n} i")

    assert "<m:oMathPara" in omml
    assert "<m:nary>" in omml
    assert f'<m:chr m:val="{chr(0x2211)}"/>' in omml
    assert "<m:sub>" in omml
    assert "<m:sup>" in omml
    assert "<m:t>i</m:t>" in omml
    assert "<m:t>n</m:t>" in omml


def test_latex_to_omml_converts_integral_with_limits():
    omml = latex_to_omml(r"I = \int_{0}^{T} f_t dt")

    assert "<m:oMathPara" in omml
    assert "<m:nary>" in omml
    assert f'<m:chr m:val="{chr(0x222B)}"/>' in omml
    assert "<m:sub>" in omml
    assert "<m:sup>" in omml
    assert "<m:t>0</m:t>" in omml
    assert "<m:t>T</m:t>" in omml


def test_latex_to_omml_rejects_unsupported_latex_macros():
    assert latex_to_omml(r"x = \unknown{x}") == ""


def test_latex_to_omml_rejects_malformed_scripts():
    assert latex_to_omml("x_{} = y") == ""
    assert latex_to_omml("x_i_j = y") == ""
