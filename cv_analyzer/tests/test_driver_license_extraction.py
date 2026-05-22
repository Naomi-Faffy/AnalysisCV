from cv_analyzer.cv_parser import CVParser


def test_extract_driver_license_accepts_exact_phrase_with_any_casing():
    parser = CVParser()

    assert parser.extract_driver_license("Driver's License") is True
    assert parser.extract_driver_license("driver's license") is True
    assert parser.extract_driver_license("dRiVeR'S lIcEnSe") is True
    assert parser.extract_driver_license("Driver’s Licence") is True


def test_extract_driver_license_rejects_near_matches():
    parser = CVParser()

    assert parser.extract_driver_license("driver license") is False
    assert parser.extract_driver_license("drivers license") is False
    assert parser.extract_driver_license("driving license") is False
    assert parser.extract_driver_license("licensed driver") is False
    assert parser.extract_driver_license("driver permit") is False