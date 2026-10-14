from disputelens.scope_invariance import norm, order


def test_norm_collapses_whitespace_and_hyphen_gaps():
    assert norm('a  fraud- related\n reason') == 'a fraud-related reason'


def test_order_sorts_by_page_then_paragraph_numerically():
    ids = ['x:page-10:paragraph-2', 'x:page-9:paragraph-11', 'x:page-9:paragraph-3']
    assert sorted(ids, key=order) == ['x:page-9:paragraph-3', 'x:page-9:paragraph-11', 'x:page-10:paragraph-2']
