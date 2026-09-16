from resume_agent.text_extract import count_job_segments, parse_card_text


def test_parse_age_and_years() -> None:
    parsed = parse_card_text("张三 30岁 5年 本科 示例科技有限公司")
    assert parsed.age == 30
    assert parsed.years == 5.0
    assert "示例科技" in parsed.org or parsed.org != ""


def test_count_job_segments_from_ranges() -> None:
    text = "工作经历 2020.01-2022.06 甲公司 2022.07-至今 乙公司"
    assert count_job_segments(text) == 2
