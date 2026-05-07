from interview import select_questions


def test_interview_question_counts_are_supported() -> None:
    assert len(select_questions(6)) == 6
    assert len(select_questions(20)) == 20
    assert len(select_questions(50)) == 50


def test_interview_question_shapes_include_recommendation_option() -> None:
    questions = select_questions(6)
    assert all(any(option["id"] == "recommend" for option in question.options) for question in questions)

