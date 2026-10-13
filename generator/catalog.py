"""Reference data for Cedar Fork Health, a fictional regional health system.

Every name, number and organization in this repository is invented.
"""

COMPANY = "Cedar Fork Health"
EMAIL_DOMAIN = "cedarforkhealth.example"

LOCATIONS = [
    # id, name, type
    ("LOC01", "Cedar Fork Medical Center", "Flagship hospital"),
    ("LOC02", "Northgate Community Hospital", "Community hospital"),
    ("LOC03", "Riverside Community Hospital", "Community hospital"),
    ("LOC04", "Cedar Fork Clinics", "Ambulatory network"),
    ("LOC05", "Corporate Center", "Administrative campus"),
]

# dept_id, name, division, is_clinical, location rule
DEPARTMENTS = [
    ("D101", "Medical-Surgical Nursing", "Nursing & Patient Care", 1, "hospital"),
    ("D102", "Intensive Care", "Nursing & Patient Care", 1, "hospital"),
    ("D103", "Emergency Department", "Nursing & Patient Care", 1, "hospital"),
    ("D104", "Labor & Delivery", "Nursing & Patient Care", 1, "hospital"),
    ("D105", "Perioperative Services", "Nursing & Patient Care", 1, "hospital"),
    ("D106", "Oncology", "Nursing & Patient Care", 1, "flagship"),
    ("D107", "Behavioral Health", "Nursing & Patient Care", 1, "hospital"),
    ("D201", "Radiology", "Clinical Support", 1, "hospital"),
    ("D202", "Laboratory", "Clinical Support", 1, "hospital"),
    ("D203", "Pharmacy", "Clinical Support", 1, "hospital"),
    ("D204", "Respiratory Therapy", "Clinical Support", 1, "hospital"),
    ("D205", "Rehabilitation Services", "Clinical Support", 1, "hospital"),
    ("D301", "Primary Care Clinics", "Physician Enterprise", 1, "clinics"),
    ("D302", "Specialty Clinics", "Physician Enterprise", 1, "clinics"),
    ("D303", "Hospital Medicine", "Physician Enterprise", 1, "hospital"),
    ("D401", "Environmental Services", "Operations", 0, "hospital"),
    ("D402", "Food & Nutrition", "Operations", 0, "hospital"),
    ("D403", "Security", "Operations", 0, "hospital"),
    ("D404", "Patient Access", "Operations", 0, "any"),
    ("D501", "Revenue Cycle & Coding", "Corporate Services", 0, "corporate"),
    ("D502", "Information Technology", "Corporate Services", 0, "corporate"),
    ("D503", "Human Resources", "Corporate Services", 0, "corporate"),
    ("D504", "Finance", "Corporate Services", 0, "corporate"),
    ("D505", "Executive Administration", "Corporate Services", 0, "corporate"),
]

NURSING_DEPTS = ["D101", "D102", "D103", "D104", "D105", "D106", "D107"]
CLINIC_DEPTS = ["D301", "D302"]

# job_code, title, family, grade, flsa, is_clinical, pay_basis, range_min, range_max,
# share of starting headcount, annual turnover base rate, departments, typical applicants per req,
# mean days to fill
JOBS = [
    ("RN100", "Registered Nurse", "Nursing", 8, "Nonexempt", 1, "Hourly", 36.0, 58.0, 0.270, 0.18, NURSING_DEPTS + CLINIC_DEPTS, 16, 52),
    ("RN200", "Charge Nurse", "Nursing", 9, "Nonexempt", 1, "Hourly", 42.0, 64.0, 0.035, 0.11, NURSING_DEPTS, 6, 45),
    ("RN300", "Nurse Manager", "Nursing Leadership", 12, "Exempt", 1, "Salary", 112000, 168000, 0.012, 0.10, NURSING_DEPTS, 9, 75),
    ("LP100", "Licensed Practical Nurse", "Nursing", 6, "Nonexempt", 1, "Hourly", 25.0, 37.0, 0.030, 0.22, ["D101", "D107"] + CLINIC_DEPTS, 14, 38),
    ("PC100", "Patient Care Technician", "Patient Care Support", 3, "Nonexempt", 1, "Hourly", 16.5, 23.5, 0.095, 0.33, NURSING_DEPTS, 34, 30),
    ("RT100", "Respiratory Therapist", "Allied Health", 7, "Nonexempt", 1, "Hourly", 31.0, 46.0, 0.020, 0.14, ["D204"], 9, 48),
    ("RD100", "Radiologic Technologist", "Allied Health", 7, "Nonexempt", 1, "Hourly", 30.0, 45.0, 0.025, 0.15, ["D201"], 11, 44),
    ("LB100", "Medical Laboratory Scientist", "Allied Health", 7, "Nonexempt", 1, "Hourly", 31.0, 47.0, 0.020, 0.13, ["D202"], 8, 50),
    ("PH100", "Pharmacist", "Pharmacy", 11, "Exempt", 1, "Salary", 128000, 162000, 0.010, 0.08, ["D203"], 7, 60),
    ("PH200", "Pharmacy Technician", "Pharmacy", 4, "Nonexempt", 1, "Hourly", 18.5, 26.0, 0.015, 0.24, ["D203"], 22, 32),
    ("PT100", "Physical Therapist", "Allied Health", 9, "Exempt", 1, "Salary", 82000, 112000, 0.015, 0.12, ["D205"], 8, 55),
    ("ST100", "Surgical Technologist", "Allied Health", 5, "Nonexempt", 1, "Hourly", 24.0, 35.0, 0.015, 0.19, ["D105"], 12, 40),
    ("MD100", "Physician", "Physicians", 15, "Exempt", 1, "Salary", 245000, 420000, 0.030, 0.06, ["D301", "D302", "D303"], 5, 120),
    ("AP100", "Advanced Practice Provider", "Advanced Practice", 13, "Exempt", 1, "Salary", 118000, 158000, 0.030, 0.10, ["D301", "D302", "D303", "D103"], 9, 80),
    ("MA100", "Medical Assistant", "Patient Care Support", 3, "Nonexempt", 1, "Hourly", 17.0, 24.0, 0.050, 0.26, CLINIC_DEPTS, 28, 28),
    ("PA100", "Patient Access Representative", "Patient Access", 2, "Nonexempt", 0, "Hourly", 16.0, 22.0, 0.050, 0.29, ["D404"], 38, 26),
    ("EV100", "Environmental Services Technician", "Support Services", 1, "Nonexempt", 0, "Hourly", 15.0, 20.0, 0.060, 0.31, ["D401"], 42, 24),
    ("FS100", "Food Service Worker", "Support Services", 1, "Nonexempt", 0, "Hourly", 15.0, 19.5, 0.030, 0.36, ["D402"], 36, 22),
    ("SC100", "Security Officer", "Support Services", 2, "Nonexempt", 0, "Hourly", 17.5, 24.0, 0.015, 0.22, ["D403"], 24, 30),
    ("CD100", "Medical Coder", "Revenue Cycle", 5, "Nonexempt", 0, "Hourly", 23.0, 33.0, 0.020, 0.14, ["D501"], 30, 35),
    ("IT100", "IT Analyst", "Information Technology", 8, "Exempt", 0, "Salary", 72000, 108000, 0.020, 0.12, ["D502"], 55, 46),
    ("HR100", "HR Specialist", "Human Resources", 6, "Exempt", 0, "Salary", 54000, 76000, 0.010, 0.14, ["D503"], 48, 38),
    ("FN100", "Financial Analyst", "Finance", 7, "Exempt", 0, "Salary", 64000, 92000, 0.012, 0.13, ["D504"], 44, 40),
    ("AD100", "Administrative Assistant", "Administrative", 3, "Nonexempt", 0, "Hourly", 18.0, 25.0, 0.030, 0.16, ["D101", "D201", "D301", "D302", "D503", "D504", "D505"], 46, 27),
    ("MG100", "Manager", "Management", 11, "Exempt", 0, "Salary", 92000, 135000, 0.020, 0.09, ["D401", "D402", "D404", "D501", "D502", "D503", "D504", "D201", "D202"], 26, 62),
    ("DR100", "Director", "Management", 13, "Exempt", 0, "Salary", 138000, 198000, 0.008, 0.08, ["D505", "D502", "D501", "D101", "D201", "D301"], 18, 85),
]

PROMOTION_PATHS = {
    "PC100": "LP100",
    "LP100": "RN100",
    "RN100": "RN200",
    "RN200": "RN300",
    "PH200": "PH100",
    "MA100": "LP100",
    "PA100": "AD100",
    "AD100": "HR100",
    "CD100": "FN100",
    "IT100": "MG100",
    "HR100": "MG100",
    "FN100": "MG100",
    "MG100": "DR100",
    "EV100": "SC100",
}

FEMALE_SHARE = {
    "Nursing": 0.88, "Nursing Leadership": 0.82, "Patient Care Support": 0.84, "Allied Health": 0.64,
    "Pharmacy": 0.60, "Physicians": 0.46, "Advanced Practice": 0.78, "Patient Access": 0.80,
    "Support Services": 0.48, "Revenue Cycle": 0.86, "Information Technology": 0.32,
    "Human Resources": 0.80, "Finance": 0.58, "Administrative": 0.90, "Management": 0.62,
}

# Shares of the 24/7 workforce by shift (hourly clinical roles in hospital departments)
SHIFTS = [("Day", 0.55), ("Evening", 0.20), ("Night", 0.25)]

VOLUNTARY_REASONS = [
    ("Better pay elsewhere", 0.24),
    ("Career advancement", 0.16),
    ("Schedule or work-life balance", 0.15),
    ("Relocation", 0.11),
    ("Workload or burnout", 0.12),
    ("Personal or family", 0.10),
    ("Return to school", 0.05),
    ("Retirement", 0.07),
]
INVOLUNTARY_REASONS = [
    ("Performance", 0.36),
    ("Attendance", 0.30),
    ("Policy violation", 0.18),
    ("Failed introductory period", 0.12),
    ("Position eliminated", 0.04),
]

SOURCES = [
    ("Career site", 0.30),
    ("Job boards", 0.24),
    ("Employee referral", 0.16),
    ("Agency or recruiter", 0.08),
    ("School partnership", 0.10),
    ("Social media", 0.07),
    ("Rehire", 0.05),
]

# category, subcategory, monthly cases per 1,000 employees, median hours to resolve, tier
CASE_TYPES = [
    ("Payroll", "Pay discrepancy", 18, 30, 1),
    ("Payroll", "Direct deposit or tax form", 10, 10, 1),
    ("Payroll", "Timekeeping correction", 14, 18, 1),
    ("Benefits", "Enrollment or coverage", 16, 26, 1),
    ("Benefits", "Dependent verification", 5, 40, 1),
    ("Leave", "FMLA or leave of absence", 9, 70, 2),
    ("Leave", "Return to work", 4, 50, 2),
    ("Employee data", "Address, name or banking change", 12, 6, 1),
    ("Employee data", "Employment verification", 7, 8, 1),
    ("Policy", "Policy question", 10, 12, 1),
    ("Onboarding", "New hire paperwork or access", 9, 20, 1),
    ("Offboarding", "Final pay or separation", 5, 36, 1),
    ("Compensation", "Pay range or increase question", 5, 60, 2),
    ("Employee relations", "Concern or complaint", 3, 160, 2),
]

FIRST_NAMES_F = """Avery Brianna Camila Danielle Elena Fatima Gabriela Hannah Imani Jasmine Kayla Leah Maya Nadia Olivia
Priya Quinn Rosa Sofia Tamara Uma Valeria Whitney Ximena Yesenia Zoe Alicia Bethany Chloe Destiny Emily Grace Isabel
Janelle Keisha Lauren Mariana Natalie Paige Renee Sarah Tiffany Vanessa Wendy Yolanda Adriana Brooke Carmen Diana Erin
Faith Gloria Hope Ivy Jada Kimberly Lucia Monica Nicole Patricia Rebecca Sandra Teresa Veronica Alejandra Bianca""".split()
FIRST_NAMES_M = """Aaron Bryan Carlos Darnell Ethan Felipe Gavin Hector Isaac Jamal Kevin Luis Marcus Nathan Omar Pedro
Rahul Samuel Trevor Victor Wesley Xavier Yusuf Andre Brandon Caleb Diego Elijah Francisco Gregory Hugo Ivan Jerome Kyle
Lamar Miguel Noah Oscar Patrick Ricardo Steven Terrell Vincent Adrian Benjamin Cesar Derek Eduardo Frank Javier""".split()
LAST_NAMES = """Adams Alvarez Anderson Baker Banks Barnes Bell Bennett Brooks Brown Bryant Butler Campbell Carter Castillo
Chavez Clark Coleman Collins Cook Cooper Cruz Davis Diaz Edwards Ellis Evans Fisher Flores Foster Garcia Gomez Gonzalez
Gordon Graham Gray Green Griffin Gutierrez Hall Hamilton Harris Hayes Henderson Hernandez Hill Holmes Howard Hughes
Jackson James Jenkins Jimenez Johnson Jones Jordan Kelly Kennedy Kim King Lee Lewis Long Lopez Marshall Martin Martinez
Mendoza Miller Mitchell Moore Morales Morgan Morris Murphy Myers Nelson Nguyen Ortiz Owens Parker Patel Perez Perry
Peterson Phillips Powell Price Ramirez Ramos Reed Reyes Reynolds Richardson Rivera Roberts Robinson Rodriguez Rogers
Ross Russell Sanchez Sanders Scott Shah Simmons Smith Stewart Sullivan Taylor Thomas Thompson Torres Tran Turner Vasquez
Walker Wallace Ward Washington Watson White Williams Wilson Wood Wright Young""".split()
