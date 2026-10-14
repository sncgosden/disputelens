from disputelens.scope_detector_v3 import heading_words, stem, subtype_established, unestablished_v3

G = ['Guide', 'Chapter 2', 'Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854)']


def test_stem_and_heading_words():
    assert stem('described') == 'describ' and stem('cat') == 'cat'
    assert heading_words('Goods or Services Were Either Not as Described or Defective') == {'describ', 'defective'}


def test_subtype_described_in_question_clears_inherited_codes():
    h = G + ['Goods or Services Were Either Not as Described or Defective', 'Issuer Chargeback']
    assert unestablished_v3(h, 'The jacket was not as described and the colour is wrong') == []


def test_generic_question_still_flagged():
    h = G + ['Counterfeit Goods', 'Issuer Chargeback']
    assert unestablished_v3(h, 'What documents must the issuer provide?') == ['4850', '4853', '4854']


def test_description_of_one_subtype_does_not_clear_another():
    h = G + ['Timeshares', 'Issuer Chargeback']
    assert not subtype_established(h, 'My customer says the item was a counterfeit')
    assert unestablished_v3(h, 'My customer says the item was a counterfeit')


def test_phrase_qualifier_survives():
    h = G + ['Installment Billing Dispute-Participating Countries (Reason Code 4850)', 'Issuer Chargeback']
    out = unestablished_v3(h, 'My customer paid in installments and the billing is wrong')
    assert 'participating countries' in out
