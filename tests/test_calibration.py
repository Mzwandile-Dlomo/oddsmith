from oddsmith.odds_model.calibration import MIN_MEANINGFUL_LEGS, grade_predictions


def test_no_predictions_says_so_instead_of_claiming_calibration():
    report = grade_predictions([])

    assert report.legs == 0
    assert report.expected_hits == 0.0
    assert report.actual_hits == 0
    assert "No graded legs" in report.verdict


def test_buckets_compare_predicted_and_actual_rates():
    report = grade_predictions([(0.65, True), (0.62, False), (0.85, True)])

    by_label = {b.label: b for b in report.buckets}
    assert by_label["60–70%"].legs == 2
    assert by_label["60–70%"].predicted_rate == 0.635
    assert by_label["60–70%"].actual_rate == 0.5
    assert by_label["80%+"].actual_rate == 1.0
    assert by_label["Under 60%"].predicted_rate is None


def test_honest_probabilities_land_inside_the_expected_range():
    # 40 legs at 70%, 28 landed: exactly what the model said.
    report = grade_predictions([(0.7, i < 28) for i in range(40)])

    assert report.expected_hits == 28.0
    assert report.expected_hits_low < 28 < report.expected_hits_high
    assert report.verdict == "Hits are inside the range its own probabilities predict."


def test_overconfidence_is_called_out_once_the_sample_is_meaningful():
    # Claims 80%, lands 50%.
    report = grade_predictions([(0.8, i % 2 == 0) for i in range(40)])

    assert report.actual_hits == 20
    assert report.actual_hits < report.expected_hits_low
    assert "overconfident" in report.verdict


def test_small_samples_are_flagged_as_mostly_luck():
    report = grade_predictions([(0.7, False)] * (MIN_MEANINGFUL_LEGS - 1))

    assert "mostly luck" in report.verdict
