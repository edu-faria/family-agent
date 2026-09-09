from __future__ import annotations

from family_agent.gateway.formatting import md_to_telegram_html


def test_bold_becomes_html():
    assert md_to_telegram_html("Adicionar **Dentista (Lena)** hoje") == (
        "Adicionar <b>Dentista (Lena)</b> hoje"
    )


def test_html_specials_escaped():
    assert md_to_telegram_html("leite & pão <urgente>") == "leite &amp; pão &lt;urgente&gt;"


def test_unbalanced_marker_left_literal_not_broken_tag():
    out = md_to_telegram_html("comprar **leite")
    assert "<b>" not in out and out == "comprar **leite"


def test_code_and_italic():
    assert md_to_telegram_html("usa `add` agora") == "usa <code>add</code> agora"
    assert md_to_telegram_html("é *muito* tarde") == "é <i>muito</i> tarde"
