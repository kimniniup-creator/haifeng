from tools.run_pet_vision_genki_eval import confusion


def test_unknowns_have_explicit_denominators_and_are_not_true_negatives():
    def row(label,score,usable=True,single=True):
        return dict(label=label,smile_left=score,smile_right=score,
                    quality_usable=usable,single_face=single)
    rows=[row(1,.8),row(1,.1),row(0,.8),row(0,.1),row(1,.9,False),row(0,0,False,False)]
    result=confusion(rows,quality_gate=True)
    assert [result[k] for k in ('tp','fp','tn','fn','unknown_positive','unknown_negative')]==[1,1,1,1,1,1]
    assert result['decided']==4 and result['coverage']==.666667
    assert result['false_positive_rate_on_decided']==.5
    assert result['false_response_rate_on_all_negative']==.333333
    assert result['response_recall_on_all_positive']==.333333
    assert result['missed_or_unknown_positive']==2
    diagnostic=confusion(rows,quality_gate=False)
    assert diagnostic['tp']==2 and diagnostic['unknown_negative']==1
