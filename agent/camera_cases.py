"""Camera phrase acceptance cases shared by tests and calibration tooling."""

# (matrix id, isolated camera phrase, expected acronym; None means reject)
CAMERA_CASES = (
    ("A1", "CTE", "CTE"),
    ("A2", "Central Expressway", "CTE"),
    ("A3", "cte", "CTE"),
    ("A4", "Kranji Highway", "KJE"),
    ("A5", "Tampines Parkway", "TPE"),
    ("A6", "East Coast", "ECP"),
    ("A7", "Tampines", "TPE"),
    ("A8", "Tampines Expresway", "TPE"),
    ("A9", "Kranjee Expressway", "KJE"),
    ("A10", "Kallang-Paya Lebar Expressway", "KPE"),
    ("A11", "Kallang Paya Lebar", "KPE"),
    ("A12", "Marina Coastal", "MCE"),
    ("A13", "Pan Island", "PIE"),
    ("A14", "TPY", None),
    ("A15", "KJE", "KJE"),
    ("A16", "Jurong Expressway", None),
    ("A20", "the expressway", None),
)
