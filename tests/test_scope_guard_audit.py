from disputelens.scope_guard_audit import unresolved_scope


def test_unknown_membership_and_country_name_do_not_authorize_participating_section():
    headings = ['Installment Billing Dispute-Participating Countries (Reason Code 4850)']
    assert unresolved_scope(headings)
    assert unresolved_scope(headings, {'region': 'UK'})
    assert unresolved_scope(headings, {'participating_countries_membership': False})
    assert not unresolved_scope(headings, {'participating_countries_membership': True})


def test_reviewed_refund_path_cannot_authorize_another_reason_code():
    reviewed = ['No-Show Hotel Charge', 'Acquirer Second Presentment', 'Refund previously issued']
    other = ['Issuer Dispute of a Recurring Transaction', 'Acquirer Second Presentment', 'Refund previously issued']
    settings = {'reviewed_refund_section_path': reviewed}
    assert not unresolved_scope(reviewed, settings)
    assert unresolved_scope(other, settings)
    assert unresolved_scope(reviewed)


def test_nested_heading_scope_does_not_disappear_at_specific_subsection():
    headings = ['Installment Billing Dispute-Participating Countries (Reason Code 4850)',
                'Issuer chargeback', 'Subsequent installments']
    assert unresolved_scope(headings)


def test_general_code_distinction_and_provider_controls_are_not_targeted():
    assert not unresolved_scope(['No Cardholder Authorization (Message Reason Code 4837/37)'])
    assert not unresolved_scope(['Visa Allocation Flow', 'Chargeback'])
    assert not unresolved_scope(['Establishing proof of shipment or proof of delivery'])
