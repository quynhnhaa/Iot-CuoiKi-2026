from scripts.check_yolov7_resume import expected_lr_factor


def test_cosine_lr_matches_saved_epoch():
    # From the 30-epoch baseline: after epoch 5, base LR 0.01 becomes 0.009397114.
    assert abs(0.01 * expected_lr_factor(5, 30, 0.1, False) - 0.009397114) < 1e-8


def test_linear_lr_endpoints():
    assert expected_lr_factor(0, 30, 0.1, True) == 1
    assert abs(expected_lr_factor(29, 30, 0.1, True) - 0.1) < 1e-12
