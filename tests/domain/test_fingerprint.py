from resume_domain.fingerprint import candidate_fingerprint


def test_fingerprint_stable_after_normalize() -> None:
    left = candidate_fingerprint(" 张三 ", "阿里巴巴")
    right = candidate_fingerprint("张三", "阿里巴巴")
    assert left == right
    assert len(left) == 64
